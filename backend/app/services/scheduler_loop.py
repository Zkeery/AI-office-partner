from __future__ import annotations

import asyncio
import logging

from app.db import session as db_session
from app.services.schedules import tick_due_schedules

logger = logging.getLogger(__name__)


async def scheduler_loop(stop_event: asyncio.Event, interval_sec: float = 30.0) -> None:
    while not stop_event.is_set():
        db = db_session.SessionLocal()
        try:
            n = await tick_due_schedules(db)
            if n:
                logger.info("scheduler ran %s due jobs", n)
        except Exception:
            logger.exception("scheduler tick failed")
        finally:
            db.close()
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
        except asyncio.TimeoutError:
            continue
