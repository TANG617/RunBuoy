from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from runbuoy.config import Config
from runbuoy.pairing import flow


class Credentials:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        self.values[name] = value

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


def test_qr_is_safe_canonical_and_shown_before_first_poll(monkeypatch: Any) -> None:
    ordering: list[str] = []

    class Client:
        def __init__(self, _config: Any, _credentials: Any) -> None:
            pass

        def create_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
            assert "machine" not in payload
            assert payload["machine_id"] == "machine-stable"
            return {
                "pairing_session_id": "pair/id",
                "challenge": "challenge + /",
                "exchange_secret": "never-in-qr",
                "bootstrap_token": "never-in-output",
                "short_code": "123456",
            }

        def pairing_status(self, _session: str, _secret: str) -> dict[str, Any]:
            ordering.append("poll")
            return {"status": "claimed"}

        def exchange_pairing(self, _session: str, _secret: str) -> dict[str, Any]:
            return {"machine_id": "machine-1", "credential": "long-lived"}

        def close(self) -> None:
            pass

    monkeypatch.setattr(flow, "RemoteClient", Client)
    credentials = Credentials()

    def created(value: dict[str, Any], qr: str) -> None:
        ordering.append("shown")
        assert "exchange_secret" not in value
        assert "bootstrap_token" not in value
        parsed = urlparse(qr)
        assert parsed.scheme == "runbuoy"
        assert parsed.netloc == "pair"
        assert parsed.path == "/pair%2Fid"
        assert "+" not in parsed.query
        assert "Mac%20Studio%20%2F%20Lab" in parsed.query
        query = parse_qs(parsed.query)
        assert query["challenge"] == ["challenge + /"]
        assert query["machine"] == ["Mac Studio / Lab"]
        assert "never-in-qr" not in qr

    result, _qr = flow.pair_machine(
        Config(machine_id="machine-stable", machine_name="Mac Studio / Lab"),
        credentials,  # type: ignore[arg-type]
        on_created=created,
    )
    assert ordering == ["shown", "poll"]
    assert result["status"] == "paired"
    assert credentials.values["machine_credential"] == "long-lived"
    assert flow.PENDING_SESSION_KEY not in credentials.values
    assert flow.PENDING_SECRET_KEY not in credentials.values


def test_no_wait_saves_pending_pairing_for_resume(monkeypatch: Any) -> None:
    class Client:
        def __init__(self, _config: Any, _credentials: Any) -> None:
            pass

        def create_pairing(self, _payload: dict[str, Any]) -> dict[str, str]:
            return {
                "pairing_session_id": "pending-session",
                "challenge": "pending-challenge",
                "exchange_secret": "pending-secret",
            }

        def close(self) -> None:
            pass

    monkeypatch.setattr(flow, "RemoteClient", Client)
    credentials = Credentials()
    flow.pair_machine(
        Config(machine_id="machine-stable"),
        credentials,  # type: ignore[arg-type]
        wait=False,
    )
    assert credentials.values[flow.PENDING_SESSION_KEY] == "pending-session"
    assert credentials.values[flow.PENDING_SECRET_KEY] == "pending-secret"


def test_resume_pairing_exchanges_saved_pending_secret(monkeypatch: Any) -> None:
    class Client:
        def __init__(self, _config: Any, _credentials: Any) -> None:
            pass

        def pairing_status(self, session: str, secret: str) -> dict[str, str]:
            assert session == "pending-session"
            assert secret == "pending-secret"
            return {"status": "claimed"}

        def exchange_pairing(self, session: str, secret: str) -> dict[str, str]:
            assert session == "pending-session"
            assert secret == "pending-secret"
            return {"machine_credential": "long-lived"}

        def close(self) -> None:
            pass

    monkeypatch.setattr(flow, "RemoteClient", Client)
    credentials = Credentials()
    credentials.set(flow.PENDING_SESSION_KEY, "pending-session")
    credentials.set(flow.PENDING_SECRET_KEY, "pending-secret")
    result = flow.resume_pairing(
        Config(machine_id="machine-stable"),
        credentials,  # type: ignore[arg-type]
    )
    assert result["status"] == "paired"
    assert credentials.values["machine_credential"] == "long-lived"
    assert flow.PENDING_SESSION_KEY not in credentials.values
    assert flow.PENDING_SECRET_KEY not in credentials.values
