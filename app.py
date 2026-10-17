# app.py
"""Main entry point for the Durga Puja Mandap Entry Management app.
It starts a Flask web server for inspection UI and registers APScheduler background jobs
that perform reservation fetching, calendar sync, rule enforcement, and daily summary generation.
"""
import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Ensure src is on the import path
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in os.sys.path:
    os.sys.path.insert(0, SRC_DIR)

from src.registry import fetch_and_store_reservations, enforce_rules_and_count
from src.summary import generate_and_send_summary

# Load configuration (simple yaml loader)
import yaml
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.config["JSONIFY_PRETTYPRINT_REGULAR"] = True

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Scheduler
scheduler = BackgroundScheduler()

def schedule_jobs():
    # Job 1: fetch reservations (e.g., daily at 06:00)
    fetch_cron = config.get("schedule", {}).get("fetch_reservations", "0 6 * * *")
    scheduler.add_job(
        func=fetch_and_store_reservations,
        trigger=CronTrigger.from_crontab(fetch_cron),
        id="fetch_reservations",
        name="Fetch reservations and update registry",
        replace_existing=True,
    )
    # Job 2: enforce rules / count entries (run shortly after fetch)
    scheduler.add_job(
        func=enforce_rules_and_count,
        trigger='interval',
        minutes=5,
        id="enforce_rules",
        name="Enforce non‑Hindu‑first rule and update counts",
        replace_existing=True,
    )
    # Job 3: generate daily summary (e.g., 07:00)
    summary_cron = config.get("schedule", {}).get("generate_summary", "0 7 * * *")
    scheduler.add_job(
        func=generate_and_send_summary,
        trigger=CronTrigger.from_crontab(summary_cron),
        id="daily_summary",
        name="Generate daily executive summary",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started with jobs: %s", scheduler.get_jobs())

# Flask routes for inspection UI
@app.route('/')
def index():
    """Render a simple dashboard showing latest counts and any validation errors."""
    # Load latest JSON counts if available
    data_dir = os.path.join(BASE_DIR, "data")
    latest_json = None
    if os.path.isdir(data_dir):
        files = sorted([f for f in os.listdir(data_dir) if f.startswith('daily_counts_') and f.endswith('.json')])
        if files:
            latest_path = os.path.join(data_dir, files[-1])
            with open(latest_path, "r", encoding="utf-8") as jf:
                latest_json = jf.read()
    return render_template('index.html', latest_json=latest_json)

@app.route('/api/status')
def api_status():
    """Return JSON with scheduler job statuses."""
    jobs = [{"id": job.id, "next_run": str(job.next_run_time)} for job in scheduler.get_jobs()]
    return jsonify({"jobs": jobs, "timestamp": datetime.utcnow().isoformat() + 'Z'})


# app.py (add below existing routes)

@app.route('/dashboard')
def dashboard():
    """Render the real‑time footfall dashboard."""
    return render_template('dashboard.html')

# app.py (add)
from src.realtime import socketio, start_background_generator

# Attach SocketIO to the Flask app
socketio.init_app(app)

# In the main entry point, start the generator before the server starts
if __name__ == '__main__':
    start_background_generator()
    socketio.run(app, host=config.get('app', {}).get('host', '0.0.0.0'),
                     port=config.get('app', {}).get('port', 5000),
                     debug=config.get('app', {}).get('debug', False))
if __name__ == '__main__':
    schedule_jobs()
    app.run(host=config.get('app', {}).get('host', '0.0.0.0'),
            port=config.get('app', {}).get('port', 5000),
            debug=config.get('app', {}).get('debug', False))
