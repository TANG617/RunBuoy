from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.models import Notification, Workspace
from app.security import new_id
from tests.conftest import Harness
from tests.test_api import auth, event, post_events


def current_revision(harness: Harness, workspace_id: str) -> int:
    with harness.session_factory() as session:
        workspace = session.get(Workspace, workspace_id)
        assert workspace is not None
        return workspace.revision


def pair_machine(
    harness: Harness,
    device: dict[str, str],
    machine_id: str,
) -> dict[str, Any]:
    created = harness.client.post(
        "/v1/pairing-sessions",
        json={"machine_id": machine_id, "display_name": machine_id},
    ).json()
    claimed = harness.client.post(
        f"/v1/pairing-sessions/{created['pairing_session_id']}/claim",
        headers=auth(device["credential"]),
        json={"challenge": created["challenge"]},
    )
    assert claimed.status_code == 200, claimed.text
    exchanged = harness.client.post(
        f"/v1/pairing-sessions/{created['pairing_session_id']}/exchange",
        json={"exchange_secret": created["exchange_secret"]},
    )
    assert exchanged.status_code == 200, exchanged.text
    return exchanged.json()


def terminal_run(
    harness: Harness,
    machine: dict[str, Any],
    *,
    at: datetime,
) -> str:
    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    response = post_events(
        harness,
        machine,
        run_id,
        [
            event(run_id, machine["machine_id"], 1, "run.started", at=at),
            event(
                run_id,
                machine["machine_id"],
                2,
                "run.succeeded",
                at=at + timedelta(seconds=1),
            ),
        ],
    )
    assert response.status_code == 200, response.text
    return run_id


def test_sync_revision_etag_and_device_visible_mutations(harness: Harness) -> None:
    device, machine = harness.pair()
    revision_after_pair = current_revision(harness, device["workspace_id"])
    assert revision_after_pair == 1

    first = harness.client.get("/v1/sync", headers=auth(device["credential"]))
    assert first.status_code == 200, first.text
    assert first.json()["schema_version"] == 1
    assert first.json()["next_cursor"] == revision_after_pair
    assert first.json()["server_time"]
    assert first.headers["etag"] == f'"sync-{device["workspace_id"]}-{revision_after_pair}"'

    assert (
        harness.client.get(
            "/v1/sync",
            params={"cursor": revision_after_pair},
            headers=auth(device["credential"]),
        ).status_code
        == 304
    )
    assert (
        harness.client.get(
            "/v1/sync",
            headers={**auth(device["credential"]), "If-None-Match": first.headers["etag"]},
        ).status_code
        == 304
    )
    assert (
        harness.client.get(
            "/v1/sync",
            params={"cursor": revision_after_pair + 100},
            headers=auth(device["credential"]),
        ).status_code
        == 409
    )

    renamed = harness.client.patch(
        f"/v1/machines/{machine['machine_id']}",
        headers=auth(machine["credential"]),
        json={"display_name": "Renamed"},
    )
    assert renamed.status_code == 200
    after_rename = current_revision(harness, device["workspace_id"])
    assert after_rename > revision_after_pair

    run_id = str(uuid.uuid4())
    harness.register_run(machine, run_id)
    after_run = current_revision(harness, device["workspace_id"])
    assert after_run > after_rename
    assert (
        post_events(
            harness,
            machine,
            run_id,
            [event(run_id, machine["machine_id"], 1, "run.started")],
        ).status_code
        == 200
    )
    after_event = current_revision(harness, device["workspace_id"])
    assert after_event > after_run

    sent = harness.client.post(
        "/v1/notifications",
        headers=auth(machine["credential"]),
        json={"title": "Visible", "body": "Revision bump"},
    )
    assert sent.status_code == 201
    after_notification = current_revision(harness, device["workspace_id"])
    assert after_notification > after_event

    sync = harness.client.get(
        "/v1/sync",
        params={"cursor": revision_after_pair},
        headers=auth(device["credential"]),
    )
    assert sync.status_code == 200
    assert sync.json()["next_cursor"] == after_notification
    assert sync.json()["runs"][0]["id"] == run_id
    assert sync.json()["machines"][0]["display_name"] == "Renamed"
    assert sync.json()["notifications"][0]["id"] == sent.json()["id"]

    subscription_id = sync.json()["machines"][0]["subscription_id"]
    deleted = harness.client.delete(
        f"/v1/machine-subscriptions/{subscription_id}",
        headers=auth(device["credential"]),
    )
    assert deleted.status_code == 204
    assert current_revision(harness, device["workspace_id"]) > after_notification


def test_sync_revision_is_persistent_and_workspace_scoped(harness: Harness) -> None:
    first_device = harness.bootstrap("workspace-one")
    second_device = harness.bootstrap("workspace-two")
    pair_machine(harness, first_device, "machine_one")
    first_revision = current_revision(harness, first_device["workspace_id"])
    second_revision = current_revision(harness, second_device["workspace_id"])

    pair_machine(harness, second_device, "machine_two")

    assert current_revision(harness, first_device["workspace_id"]) == first_revision
    assert current_revision(harness, second_device["workspace_id"]) > second_revision
    first_sync = harness.client.get("/v1/sync", headers=auth(first_device["credential"]))
    second_sync = harness.client.get("/v1/sync", headers=auth(second_device["credential"]))
    assert [item["id"] for item in first_sync.json()["machines"]] == ["machine_one"]
    assert [item["id"] for item in second_sync.json()["machines"]] == ["machine_two"]
    # Read through a fresh Session to prove the value is stored in the database,
    # rather than process memory.
    with harness.session_factory() as session:
        persisted = session.scalar(
            select(Workspace.revision).where(Workspace.id == first_device["workspace_id"])
        )
    assert persisted == first_revision


def test_revoke_and_device_reset_advance_workspace_revision(harness: Harness) -> None:
    device, machine = harness.pair()
    before_revoke = current_revision(harness, device["workspace_id"])

    revoked = harness.client.post(
        f"/v1/machines/{machine['machine_id']}/revoke",
        headers=auth(device["credential"]),
    )

    assert revoked.status_code == 204
    after_revoke = current_revision(harness, device["workspace_id"])
    assert after_revoke > before_revoke
    snapshot = harness.client.get(
        "/v1/sync",
        params={"cursor": before_revoke},
        headers=auth(device["credential"]),
    )
    assert snapshot.status_code == 200
    assert snapshot.json()["machines"] == []

    reset = harness.client.delete(
        f"/v1/devices/{device['device_id']}",
        headers=auth(device["credential"]),
    )

    assert reset.status_code == 204
    assert current_revision(harness, device["workspace_id"]) > after_revoke


def test_sync_snapshot_is_bounded(harness: Harness) -> None:
    device = harness.bootstrap()
    with harness.session_factory() as session:
        session.add_all(
            [
                Notification(
                    id=new_id("ntf"),
                    workspace_id=device["workspace_id"],
                    title=f"Message {index}",
                    body="Bounded",
                    level="info",
                    fields=[],
                    created_at=datetime.now(UTC) + timedelta(microseconds=index),
                )
                for index in range(205)
            ]
        )
        session.commit()

    response = harness.client.get("/v1/sync", headers=auth(device["credential"]))
    assert response.status_code == 200
    assert len(response.json()["notifications"]) == 200
    assert response.json()["history_notifications_has_more"] is True
    assert response.json()["history_notifications_next_cursor"] is not None


def test_terminal_run_history_cursor_is_stable_and_filterable(harness: Harness) -> None:
    device = harness.bootstrap()
    first_machine = pair_machine(harness, device, "machine_a")
    second_machine = pair_machine(harness, device, "machine_b")
    start = datetime(2026, 8, 1, tzinfo=UTC)
    expected_ids = [
        terminal_run(harness, first_machine, at=start + timedelta(minutes=index))
        for index in range(5)
    ]
    second_machine_id = terminal_run(harness, second_machine, at=start + timedelta(minutes=2))
    active_id = str(uuid.uuid4())
    harness.register_run(first_machine, active_id)

    first = harness.client.get(
        "/v1/history/runs",
        params={"limit": 2},
        headers=auth(device["credential"]),
    )
    assert first.status_code == 200, first.text
    first_ids = [item["id"] for item in first.json()["items"]]
    assert active_id not in first_ids
    assert first.json()["has_more"] is True

    inserted_after_cursor = terminal_run(
        harness,
        first_machine,
        at=start + timedelta(days=1),
    )
    seen = list(first_ids)
    cursor = first.json()["next_cursor"]
    while cursor is not None:
        page = harness.client.get(
            "/v1/history/runs",
            params={"limit": 2, "cursor": cursor},
            headers=auth(device["credential"]),
        )
        assert page.status_code == 200, page.text
        seen.extend(item["id"] for item in page.json()["items"])
        cursor = page.json()["next_cursor"]

    assert inserted_after_cursor not in seen
    assert len(seen) == len(set(seen)) == 6
    assert set(seen) == set([*expected_ids, second_machine_id])

    filtered = harness.client.get(
        "/v1/history/runs",
        params={"limit": 100, "machine_id": "machine_b"},
        headers=auth(device["credential"]),
    )
    assert [item["id"] for item in filtered.json()["items"]] == [second_machine_id]
    assert (
        harness.client.get(
            "/v1/history/runs",
            params={"limit": 0},
            headers=auth(device["credential"]),
        ).status_code
        == 422
    )
    assert (
        harness.client.get(
            "/v1/history/runs",
            params={"limit": 101},
            headers=auth(device["credential"]),
        ).status_code
        == 422
    )
    assert (
        harness.client.get(
            "/v1/history/runs",
            params={"cursor": "tampered"},
            headers=auth(device["credential"]),
        ).status_code
        == 400
    )
    assert (
        harness.client.get(
            "/v1/history/runs",
            params={"cursor": first.json()["next_cursor"], "machine_id": "machine_a"},
            headers=auth(device["credential"]),
        ).status_code
        == 400
    )


def test_notification_history_has_deterministic_pages(harness: Harness) -> None:
    device, machine = harness.pair()
    created_ids: list[str] = []
    for index in range(5):
        response = harness.client.post(
            "/v1/notifications",
            headers=auth(machine["credential"]),
            json={"title": f"Message {index}", "body": "Body"},
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        page = harness.client.get(
            "/v1/history/notifications",
            params=params,
            headers=auth(device["credential"]),
        )
        assert page.status_code == 200, page.text
        seen.extend(item["id"] for item in page.json()["items"])
        cursor = page.json()["next_cursor"]
        if cursor is None:
            break

    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == set(created_ids)


def test_old_collection_endpoints_keep_their_shapes(harness: Harness) -> None:
    device, machine = harness.pair()
    terminal_run(harness, machine, at=datetime.now(UTC))
    harness.client.post(
        "/v1/notifications",
        headers=auth(machine["credential"]),
        json={"title": "Legacy", "body": "Shape"},
    )

    assert isinstance(
        harness.client.get("/v1/runs", headers=auth(device["credential"])).json(),
        list,
    )
    assert isinstance(
        harness.client.get("/v1/machines", headers=auth(device["credential"])).json(), list
    )
    assert isinstance(
        harness.client.get("/v1/notifications", headers=auth(device["credential"])).json(),
        list,
    )
