from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

PROTOCOL_DIR = Path(__file__).parents[1]
FIXTURES_DIR = PROTOCOL_DIR / "fixtures"
TERMINAL_EVENTS = {
    "run.succeeded",
    "run.failed",
    "run.cancelled",
    "run.lost",
}
FORBIDDEN_REMOTE_KEYS = {
    "argv",
    "cwd",
    "env",
    "environment",
    "stdout",
    "stderr",
    "stdin",
    "token",
    "secret",
    "command",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def event_validator() -> Draft202012Validator:
    schema = load_json(PROTOCOL_DIR / "run-event.schema.json")
    schema["properties"]["payload"]["properties"]["progress"] = load_json(
        PROTOCOL_DIR / "progress.schema.json"
    )
    return Draft202012Validator(schema)


@pytest.mark.parametrize(
    "fixture_name",
    ["run-progress.json", "run-succeeded.json", "default-upload.json"],
)
def test_event_fixtures_validate(fixture_name: str) -> None:
    event_validator().validate(load_json(FIXTURES_DIR / fixture_name))


def test_unknown_fields_are_forward_compatible() -> None:
    fixture = load_json(FIXTURES_DIR / "run-progress.json")
    fixture["future_envelope_field"] = {"introduced_in": 2}
    fixture["payload"]["future_payload_field"] = True
    event_validator().validate(fixture)


def test_sequence_is_positive_and_monotonic() -> None:
    events = [
        load_json(FIXTURES_DIR / "run-progress.json"),
        load_json(FIXTURES_DIR / "run-succeeded.json"),
    ]
    assert [event["seq"] for event in events] == sorted({event["seq"] for event in events})
    invalid = events[0] | {"seq": 0}
    assert list(event_validator().iter_errors(invalid))


def project_snapshot(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Small reference projector used to lock protocol ordering semantics."""
    snapshot: dict[str, Any] = {"seq": 0, "execution_status": "CREATED"}
    terminal = False
    state_by_event = {
        "run.started": "RUNNING",
        "run.succeeded": "SUCCEEDED",
        "run.failed": "FAILED",
        "run.cancelled": "CANCELLED",
        "run.lost": "LOST",
    }
    seen_ids: set[str] = set()
    for event in events:
        if event["event_id"] in seen_ids:
            continue
        seen_ids.add(event["event_id"])
        if event["seq"] <= snapshot["seq"] or terminal:
            continue
        snapshot["seq"] = event["seq"]
        snapshot["execution_status"] = state_by_event.get(
            event["type"], snapshot["execution_status"]
        )
        terminal = event["type"] in TERMINAL_EVENTS
    return snapshot


def test_duplicates_and_out_of_order_events_do_not_regress_snapshot() -> None:
    progress = load_json(FIXTURES_DIR / "run-progress.json")
    succeeded = load_json(FIXTURES_DIR / "run-succeeded.json")
    stale = progress | {
        "event_id": "0190f2a0-b099-7abc-8def-0123456789ab",
        "seq": 41,
    }
    snapshot = project_snapshot([progress, progress, succeeded, stale])
    assert snapshot == {"seq": 43, "execution_status": "SUCCEEDED"}


def test_terminal_state_is_immutable() -> None:
    succeeded = load_json(FIXTURES_DIR / "run-succeeded.json")
    later = load_json(FIXTURES_DIR / "run-progress.json") | {
        "event_id": "0190f2a0-b100-7abc-8def-0123456789ab",
        "seq": 44,
    }
    snapshot = project_snapshot([succeeded, later])
    assert snapshot == {"seq": 43, "execution_status": "SUCCEEDED"}


def walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | set().union(
            *(walk_keys(child) for child in value.values())
        )
    if isinstance(value, list):
        return set().union(*(walk_keys(child) for child in value), set())
    return set()


def test_default_upload_has_no_sensitive_execution_data() -> None:
    fixture = load_json(FIXTURES_DIR / "default-upload.json")
    assert not (walk_keys(fixture) & FORBIDDEN_REMOTE_KEYS)


def test_openapi_contract_is_valid_and_has_no_control_paths() -> None:
    spec = yaml.safe_load((PROTOCOL_DIR / "openapi.yaml").read_text(encoding="utf-8"))
    validate(spec)
    forbidden = {
        "/cancel",
        "/retry",
        "/input",
        "/commands",
        "/execute",
        "/signal",
        "/approve",
        "/keys",
    }
    paths = "\n".join(spec["paths"]).lower()
    assert not any(fragment in paths for fragment in forbidden)
