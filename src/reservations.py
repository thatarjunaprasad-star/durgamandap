# src/reservations.py
"""Reservation ingestion utilities.

- If a REST API endpoint is configured, we use `requests` to pull JSON.
- Otherwise we fall back to Playwright headless‑browser scraping of a
  reservation page (login + table extraction) and return a list of dicts
  matching the expected schema for `registry.fetch_and_store_reservations`.
"""
import logging
from datetime import datetime
from typing import List, Dict

import requests
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

def _load_config():
    import yaml, os
    cfg_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

CONFIG = _load_config()

def _fetch_via_api() -> List[Dict]:
    api_cfg = CONFIG.get("reservation", {})
    endpoint = api_cfg.get("api_endpoint")
    token = api_cfg.get("api_token")
    if not endpoint:
        return []
    try:
        resp = requests.get(endpoint, headers={"Authorization": f"Bearer {token}"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info("API returned %d items", len(data))
        return _normalize(data)
    except Exception as e:
        logger.exception("API fetch failed: %s", e)
        return []

def _scrape_via_playwright() -> List[Dict]:
    scrape_cfg = CONFIG.get("reservation", {})
    url = scrape_cfg.get("scrape_url")
    user = scrape_cfg.get("username")
    pwd = scrape_cfg.get("password")
    if not url:
        return []
    logger.info("Launching Playwright to scrape %s", url)
    results: List[Dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url, timeout=30000)
            if user and pwd:
                page.fill('input[name="username"]', user)
                page.fill('input[name="password"]', pwd)
                page.click('button[type="submit"]')
                page.wait_for_load_state("networkidle")
            rows = page.query_selector_all("table tr")
            for row in rows[1:]:  # skip header
                cells = row.query_selector_all("td")
                if len(cells) < 4:
                    continue
                name = cells[0].inner_text().strip()
                religion = cells[1].inner_text().strip()
                reservation_id = cells[2].inner_text().strip()
                arrival_raw = cells[3].inner_text().strip()
                try:
                    arrival = datetime.fromisoformat(arrival_raw)
                except Exception:
                    arrival = datetime.now()
                results.append({
                    "name": name,
                    "religion": religion,
                    "reservation_id": reservation_id,
                    "arrival_time": arrival,
                })
        finally:
            browser.close()
    logger.info("Scrape produced %d reservations", len(results))
    return results

def _normalize(raw_items: List[Dict]) -> List[Dict]:
    out = []
    for item in raw_items:
        try:
            out.append({
                "name": item["name"],
                "religion": item["religion"],
                "reservation_id": str(item["reservation_id"]),
                "arrival_time": datetime.fromisoformat(item["arrival_time"]),
            })
        except Exception as e:
            logger.warning("Skipping malformed reservation %s: %s", item, e)
    return out

def get_latest_reservations() -> List[Dict]:
    """Public entry point used by `registry.fetch_and_store_reservations`."""
    api_res = _fetch_via_api()
    if api_res:
        return api_res
    return _scrape_via_playwright()
