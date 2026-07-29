from __future__ import annotations

from collections import defaultdict
from typing import Any

import httpx

from runbuoy import __version__
from runbuoy.config import Config, CredentialStore
from runbuoy.models import RunEvent
from runbuoy.persistence.store import EventQueue
from runbuoy.security.redaction import assert_safe_remote_payload


class RemoteError(RuntimeError):
    pass


class RemoteClient:
    def __init__(
        self,
        config: Config,
        credentials: CredentialStore,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.config = config
        token = credentials.get("machine_credential")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.client = httpx.Client(
            base_url=str(config.server_url).rstrip("/"),
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = self.client.request(method, path, **kwargs)
        if response.status_code not in {200, 201, 202, 204}:
            raise RemoteError(f"server returned HTTP {response.status_code}")
        return response

    def upsert_run(self, run: dict[str, Any]) -> None:
        # PUT establishes immutable metadata only. Ordered events are the sole source of
        # projection state, which makes a fully offline CREATED..terminal replay legal.
        payload = {
            "machine_id": run["machine_id"],
            "title": run["title"],
            "source": run["source"],
            "execution_status": "CREATED",
            "cli_version": __version__,
        }
        assert_safe_remote_payload(payload)
        self._request("PUT", f"/v1/runs/{run['run_id']}", json=payload)

    def upload_events(self, run_id: str, events: list[RunEvent]) -> None:
        payload = {"events": [event.model_dump(mode="json") for event in events]}
        assert_safe_remote_payload(payload)
        self._request("POST", f"/v1/runs/{run_id}/events:batch", json=payload)

    def notify(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert_safe_remote_payload(payload)
        response = self._request("POST", "/v1/notifications", json=payload)
        return dict(response.json()) if response.content else {"accepted": True}

    def create_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert_safe_remote_payload(payload)
        response = self._request("POST", "/v1/pairing-sessions", json=payload)
        return dict(response.json())

    def pairing_status(self, session_id: str, exchange_secret: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/v1/pairing-sessions/{session_id}",
            headers={"Authorization": f"Bearer {exchange_secret}"},
        )
        return dict(response.json())

    def exchange_pairing(self, session_id: str, exchange_secret: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            f"/v1/pairing-sessions/{session_id}/exchange",
            json={"exchange_secret": exchange_secret},
        )
        return dict(response.json())


def flush_pending(
    queue: EventQueue,
    client: RemoteClient,
    *,
    batch_size: int,
    run_id: str | None = None,
) -> int:
    events = queue.pending_events(batch_size, run_id=run_id)
    if not events:
        return 0
    grouped: dict[str, list[RunEvent]] = defaultdict(list)
    for event in events:
        grouped[event.run_id].append(event)
    delivered = 0
    for event_run_id, batch in grouped.items():
        event_ids = [event.event_id for event in batch]
        try:
            run = queue.get_run(event_run_id)
            if run is None:
                raise RemoteError(f"local run disappeared: {event_run_id}")
            if not run["remote_initialized"]:
                client.upsert_run(run)
                queue.mark_remote_initialized(event_run_id)
            client.upload_events(event_run_id, batch)
        except (httpx.HTTPError, RemoteError, OSError) as error:
            attempts = max(
                (row["attempt_count"] for row in queue.event_rows(event_run_id)),
                default=0,
            )
            queue.mark_failed(event_ids, str(error), min(2**attempts, 60))
            continue
        queue.mark_delivered(event_ids)
        delivered += len(batch)
    return delivered
