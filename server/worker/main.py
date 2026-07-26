from __future__ import annotations

import argparse
import time

from app.apns import provider_for
from app.config import Settings
from app.database import SessionLocal
from app.outbox import OutboxProcessor
from app.security import cipher_for
from app.services import cleanup_retention


def run() -> None:
    parser = argparse.ArgumentParser(description="RunBuoy APNs outbox worker")
    parser.add_argument("--once", action="store_true", help="drain once and exit")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    settings = Settings.from_env()
    settings.validate()
    provider = provider_for(settings)
    processor = OutboxProcessor(settings, provider, cipher_for(settings))
    try:
        while True:
            with SessionLocal() as session:
                processed = processor.drain(session, args.limit)
                cleanup_retention(session, settings)
                session.commit()
            if args.once:
                break
            if processed == 0:
                time.sleep(1.0)
    finally:
        provider.close()


if __name__ == "__main__":
    run()
