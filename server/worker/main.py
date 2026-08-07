from __future__ import annotations

import argparse
import json
import logging

from app.apns import provider_for
from app.config import Settings
from app.database import SessionLocal
from app.heartbeat import record_heartbeat, worker_instance_id
from app.outbox import OutboxProcessor
from app.security import cipher_for
from app.services import cleanup_retention
from worker.wakeup import OutboxWakeup

logger = logging.getLogger("runbuoy.worker")


def run() -> None:
    parser = argparse.ArgumentParser(description="RunBuoy APNs outbox worker")
    parser.add_argument("--once", action="store_true", help="drain once and exit")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.validate()
    provider = provider_for(settings)
    processor = OutboxProcessor(settings, provider, cipher_for(settings))
    wakeup = OutboxWakeup(settings.database_url)
    instance_id = worker_instance_id()
    try:
        while True:
            wait_seconds = float(settings.worker_heartbeat_interval_seconds)
            with SessionLocal() as session:
                try:
                    record_heartbeat(session, instance_id=instance_id)
                    processed = processor.drain(session, args.limit)
                    cleanup_counts = cleanup_retention(session, settings)
                    record_heartbeat(
                        session,
                        instance_id=instance_id,
                        cleanup_counts=cleanup_counts,
                    )
                    wait_seconds = min(
                        processor.seconds_until_next(session),
                        float(settings.worker_heartbeat_interval_seconds),
                    )
                except Exception as error:
                    session.rollback()
                    error_code = type(error).__name__
                    try:
                        with SessionLocal() as failure_session:
                            record_heartbeat(
                                failure_session,
                                instance_id=instance_id,
                                status="failed",
                                error_code=error_code,
                            )
                    except Exception as heartbeat_error:
                        logger.error(
                            json.dumps(
                                {
                                    "event": "worker_heartbeat_write_failed",
                                    "error_class": type(heartbeat_error).__name__,
                                },
                                separators=(",", ":"),
                                sort_keys=True,
                            )
                        )
                    logger.error(
                        json.dumps(
                            {
                                "event": "worker_loop_failed",
                                "error_class": error_code,
                            },
                            separators=(",", ":"),
                            sort_keys=True,
                        )
                    )
                    raise SystemExit(1) from None
            if args.once:
                break
            if processed == 0:
                wakeup.wait(wait_seconds)
    finally:
        wakeup.close()
        provider.close()


if __name__ == "__main__":
    run()
