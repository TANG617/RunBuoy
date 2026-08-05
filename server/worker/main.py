from __future__ import annotations

import argparse

from app.apns import provider_for
from app.config import Settings
from app.database import SessionLocal
from app.outbox import OutboxProcessor
from app.security import cipher_for
from app.services import cleanup_retention
from worker.wakeup import OutboxWakeup


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
    try:
        while True:
            with SessionLocal() as session:
                processed = processor.drain(session, args.limit)
                cleanup_retention(session, settings)
                session.commit()
                wait_seconds = processor.seconds_until_next(session)
            if args.once:
                break
            if processed == 0:
                wakeup.wait(wait_seconds)
    finally:
        wakeup.close()
        provider.close()


if __name__ == "__main__":
    run()
