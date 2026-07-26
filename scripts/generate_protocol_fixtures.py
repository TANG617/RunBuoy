#!/usr/bin/env python3
"""Generate deterministic cross-platform RunBuoy protocol fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "packages" / "protocol" / "fixtures"


def documents() -> dict[str, dict[str, Any]]:
    progress = {
        "schema_version": 1,
        "event_id": "0190f2a0-b001-7abc-8def-0123456789ab",
        "run_id": "0190f2a0-a001-7abc-8def-0123456789ab",
        "machine_id": "machine_mac_studio",
        "seq": 42,
        "type": "run.progress",
        "occurred_at": "2026-07-26T19:45:22.184Z",
        "payload": {
            "progress": {
                "kind": "determinate",
                "current": 37,
                "total": 100,
                "fraction": 0.37,
                "unit": "items",
                "source": "explicit",
                "phase": "processing",
                "message": "Processing item 37",
            },
            "phase": "processing",
            "message": "Processing item 37",
        },
    }
    return {
        "run-progress.json": progress,
        "run-succeeded.json": {
            "schema_version": 1,
            "event_id": "0190f2a0-b002-7abc-8def-0123456789ab",
            "run_id": "0190f2a0-a001-7abc-8def-0123456789ab",
            "machine_id": "machine_mac_studio",
            "seq": 43,
            "type": "run.succeeded",
            "occurred_at": "2026-07-26T19:46:01.000Z",
            "payload": {"exit_code": 0, "message": "Run completed"},
        },
        "default-upload.json": {
            "schema_version": 1,
            "event_id": "0190f2a0-b003-7abc-8def-0123456789ab",
            "run_id": "0190f2a0-a003-7abc-8def-0123456789ab",
            "machine_id": "machine_mac_studio",
            "seq": 1,
            "type": "run.created",
            "occurred_at": "2026-07-26T19:45:00.000Z",
            "payload": {
                "title": "python · experiment.py",
                "source": "cli",
                "health_status": "HEALTHY",
                "attention_status": "NONE",
            },
        },
        "live-activity-update.json": {
            "aps": {
                "timestamp": 1785075922,
                "event": "update",
                "content-state": {
                    "sequence": 42,
                    "executionStatus": "RUNNING",
                    "healthStatus": "HEALTHY",
                    "attentionStatus": "NONE",
                    "progressKind": "determinate",
                    "progress": 0.37,
                    "phase": "processing",
                    "message": "Processing item 37",
                    "startedAt": "2026-07-26T19:40:00.000Z",
                    "updatedAt": "2026-07-26T19:45:22.184Z",
                    "estimatedEndAt": None,
                    "exitCode": None,
                },
                "stale-date": 1785075982,
            }
        },
    }


def rendered(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail instead of writing when checked-in fixtures differ.",
    )
    args = parser.parse_args()
    differences: list[str] = []
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, value in documents().items():
        path = FIXTURES / name
        content = rendered(value)
        if path.exists() and path.read_text(encoding="utf-8") == content:
            continue
        if args.check:
            differences.append(name)
        else:
            path.write_text(content, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
    if differences:
        print(
            f"fixtures are stale: {', '.join(differences)}; "
            "run scripts/generate_protocol_fixtures.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
