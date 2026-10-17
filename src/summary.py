# src/summary.py
"""Daily executive‑summary generation, validation and optional email dispatch.
The module is used by the APScheduler job defined in *app.py*.
"""
import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

# Local imports – the src package is on the Python path via app.py
from src.models import SessionLocal, Visitor, Religion, DailyCountsSchema, init_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helper: load the project's ``config.yaml`` (same logic used elsewhere)
# ---------------------------------------------------------------------------
def _load_config() -> dict:
    import yaml
    cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = _load_config()

# ---------------------------------------------------------------------------
# Template environment – renders the markdown summary (templates/summary.md.j2)
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE_ENV = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")))

# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------
def _collect_counts() -> DailyCountsSchema:
    """Query the SQLite DB for today’s statistics and return a validated Pydantic model."""
    init_db()
    session = SessionLocal()
    try:
        today = date.today()
        start_dt = datetime.combine(today, datetime.min.time())
        end_dt = datetime.combine(today, datetime.max.time())
        total = session.query(Visitor).filter(Visitor.arrival_time.between(start_dt, end_dt)).count()
        hindu = (
            session.query(Visitor)
            .filter(Visitor.arrival_time.between(start_dt, end_dt), Visitor.religion == Religion.HINDU)
            .count()
        )
        non_hindu = total - hindu
        pending_non = (
            session.query(Visitor)
            .filter(
                Visitor.arrival_time.between(start_dt, end_dt),
                Visitor.religion == Religion.NON_HINDU,
                Visitor.processed.is_(False),
            )
            .count()
        )
        pending_hind = (
            session.query(Visitor)
            .filter(
                Visitor.arrival_time.between(start_dt, end_dt),
                Visitor.religion == Religion.HINDU,
                Visitor.processed.is_(False),
            )
            .count()
        )
        return DailyCountsSchema(
            date=datetime.utcnow(),
            total_visitors=total,
            hindu_visitors=hindu,
            non_hindu_visitors=non_hindu,
            pending_non_hindu=pending_non,
            pending_hindu=pending_hind,
        )
    finally:
        session.close()

def _write_json(counts: DailyCountsSchema) -> Path:
    """Persist the day’s counts as a JSON file under ``data/``.
    Returns the absolute path to the created file.
    """
    data_dir = Path(BASE_DIR) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    filename = f"daily_counts_{counts.date.strftime('%Y%m%d')}.json"
    out_path = data_dir / filename
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(counts.dict(), f, default=str, indent=2)
    logger.info("Wrote daily counts JSON to %s", out_path)
    return out_path

def _render_markdown(counts: DailyCountsSchema) -> str:
    """Render the markdown executive summary using the Jinja2 template.
    The template lives at ``templates/summary.md.j2``.
    """
    template = TEMPLATE_ENV.get_template("summary.md.j2")
    return template.render(counts=counts)

def _send_email(body_md: str, json_path: Path) -> None:
    """Send the markdown body via SMTP and attach the raw JSON payload.
    If the ``email`` section is missing or incomplete, the function logs a warning
    and skips sending.
    """
    email_cfg = CONFIG.get("email", {})
    required = {"smtp_server", "smtp_port", "sender", "recipient", "username", "password"}
    if not required.issubset(email_cfg.keys()):
        logger.warning("Email configuration incomplete – skipping email dispatch.")
        return
    from email.message import EmailMessage
    import smtplib

    msg = EmailMessage()
    msg["Subject"] = f"Durga Mandap Daily Summary – {date.today().isoformat()}"
    msg["From"] = email_cfg["sender"]
    msg["To"] = email_cfg["recipient"]
    msg.set_content(body_md)

    # Attach JSON for audit purposes
    with json_path.open("rb") as jf:
        msg.add_attachment(jf.read(), maintype="application", subtype="json", filename=json_path.name)

    try:
        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"]) as server:
            server.starttls()
            server.login(email_cfg["username"], email_cfg["password"])
            server.send_message(msg)
        logger.info("Daily summary email sent to %s", email_cfg["recipient"])
    except Exception as e:
        logger.exception("Failed to send summary email: %s", e)

# ---------------------------------------------------------------------------
# Public entry point used by the scheduler
# ---------------------------------------------------------------------------
def generate_and_send_summary() -> None:
    """Collect counts, validate them (Pydantic does this automatically),
    write JSON, render markdown, and optionally email the report.
    Any exception is logged – the scheduler will continue running.
    """
    logger.info("Starting daily summary generation")
    try:
        counts = _collect_counts()  # validation occurs here
        json_path = _write_json(counts)
        markdown_body = _render_markdown(counts)
        _send_email(markdown_body, json_path)
        logger.info("Daily summary pipeline completed successfully")
    except Exception as exc:
        logger.exception("Error in daily summary pipeline: %s", exc)
