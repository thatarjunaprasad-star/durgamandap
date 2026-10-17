# src/registry.py
"""Logic for fetching reservations, storing them in the DB, and enforcing the
non‑Hindu‑first entry rule.
"""
import logging
from datetime import datetime
from typing import List

from src.models import SessionLocal, init_db, Visitor, Religion, VisitorSchema
from src.reservations import get_latest_reservations

logger = logging.getLogger(__name__)

def fetch_and_store_reservations():
    """Fetch new reservations from the external system and insert them into the DB.
    This function is scheduled by APScheduler.
    """
    init_db()
    session = SessionLocal()
    try:
        reservations = get_latest_reservations()
        logger.info("Fetched %d reservations", len(reservations))
        for res in reservations:
            # Skip if already present (unique reservation_id)
            exists = session.query(Visitor).filter_by(reservation_id=res["reservation_id"]).first()
            if exists:
                continue
            visitor = Visitor(
                name=res["name"],
                religion=Religion(res["religion"]),
                reservation_id=res["reservation_id"],
                arrival_time=res["arrival_time"],
                processed=False,
            )
            session.add(visitor)
        session.commit()
        logger.info("Stored new reservations in DB")
    except Exception as e:
        logger.exception("Error while fetching/storing reservations: %s", e)
        session.rollback()
    finally:
        session.close()

def enforce_rules_and_count():
    """Enforce the rule that non‑Hindu visitors are admitted before Hindus.
    For each unprocessed visitor, allow entry only if there are no pending
    non‑Hindu visitors ahead in the queue.
    """
    session = SessionLocal()
    try:
        # Get all unprocessed visitors ordered by arrival_time
        pending = session.query(Visitor).filter_by(processed=False).order_by(Visitor.arrival_time).all()
        for visitor in pending:
            if visitor.religion == Religion.HINDU:
                # Check if any earlier non‑Hindu is still pending
                earlier_non_hindu = (
                    session.query(Visitor)
                    .filter(
                        Visitor.processed == False,
                        Visitor.religion == Religion.NON_HINDU,
                        Visitor.arrival_time < visitor.arrival_time,
                    )
                    .first()
                )
                if earlier_non_hindu:
                    # cannot process this Hindu yet
                    continue
            # Mark as processed (entry allowed)
            visitor.processed = True
            session.add(visitor)
        session.commit()
        logger.info("Rule enforcement run completed")
    except Exception as e:
        logger.exception("Error during rule enforcement: %s", e)
        session.rollback()
    finally:
        session.close()
