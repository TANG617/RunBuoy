from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select

from app.abuse import anonymized_key
from app.models import (
    AuditLog,
    Device,
    DeviceCredential,
    LiveActivityBinding,
    Machine,
    MachineCredential,
    MachineDeviceSubscription,
    Notification,
    PushAttempt,
    PushOutbox,
    QuotaLock,
    RateLimitBucket,
    Run,
    Workspace,
    WorkspaceDeletionChallenge,
)
from tests.conftest import Harness
from tests.test_api import auth


def pair_named(
    harness: Harness,
    *,
    installation_id: str,
    machine_id: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    device = harness.bootstrap(installation_id)
    created = harness.client.post(
        "/v1/pairing-sessions",
        json={
            "machine_id": machine_id,
            "display_name": machine_id,
            "platform": "darwin",
        },
    )
    assert created.status_code == 201
    pairing = created.json()
    claimed = harness.client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/claim",
        headers=auth(device["credential"]),
        json={"challenge": pairing["challenge"]},
    )
    assert claimed.status_code == 200, claimed.text
    exchanged = harness.client.post(
        f"/v1/pairing-sessions/{pairing['pairing_session_id']}/exchange",
        json={"exchange_secret": pairing["exchange_secret"]},
    )
    assert exchanged.status_code == 200, exchanged.text
    return device, {**pairing, **exchanged.json()}


def add_pending_push(
    harness: Harness,
    *,
    run_id: str,
    device_id: str,
    outbox_id: str = "out_pending_lifecycle",
) -> None:
    with harness.session_factory() as session:
        session.add(
            PushOutbox(
                id=outbox_id,
                kind="LIVE_START",
                target_type="device",
                target_id=device_id,
                run_id=run_id,
                desired_payload={"aps": {}},
                status="pending",
                coalesce_key=f"live-start:{run_id}:{device_id}",
            )
        )
        session.commit()


def test_stop_receiving_removes_only_owned_subscription_and_cancels_pending_push(
    harness: Harness,
) -> None:
    device, machine = harness.pair()
    run_id = "10000000-0000-4000-8000-000000000001"
    harness.register_run(machine, run_id)
    add_pending_push(harness, run_id=run_id, device_id=device["device_id"])
    machines = harness.client.get("/v1/machines", headers=auth(device["credential"])).json()
    subscription_id = machines[0]["subscription_id"]

    response = harness.client.delete(
        f"/v1/machine-subscriptions/{subscription_id}",
        headers=auth(device["credential"]),
    )

    assert response.status_code == 204
    future_notification = harness.client.post(
        "/v1/notifications",
        headers=auth(machine["credential"]),
        json={"title": "No push", "body": "Subscription is gone"},
    )
    assert future_notification.status_code == 201
    with harness.session_factory() as session:
        assert session.get(MachineDeviceSubscription, subscription_id) is None
        machine_row = session.get(Machine, machine["machine_id"])
        assert machine_row is not None and machine_row.revoked_at is None
        credential = session.scalar(
            select(MachineCredential).where(MachineCredential.machine_id == machine["machine_id"])
        )
        assert credential is not None and credential.revoked_at is None
        outbox = session.get(PushOutbox, "out_pending_lifecycle")
        assert outbox is not None and outbox.status == "cancelled"
        assert (
            session.scalar(
                select(func.count())
                .select_from(PushOutbox)
                .where(
                    PushOutbox.target_id == device["device_id"],
                    PushOutbox.status == "pending",
                )
            )
            == 0
        )
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "subscription.stop_receiving")
        )
        assert audit is not None


def test_device_can_revoke_workspace_machine_but_not_cross_workspace(harness: Harness) -> None:
    device, machine = pair_named(
        harness,
        installation_id="ios-owner",
        machine_id="machine_owner",
    )
    other_device, _other_machine = pair_named(
        harness,
        installation_id="ios-other",
        machine_id="machine_other",
    )
    run_id = "10000000-0000-4000-8000-000000000002"
    harness.register_run(machine, run_id)
    add_pending_push(harness, run_id=run_id, device_id=device["device_id"])

    denied = harness.client.post(
        f"/v1/machines/{machine['machine_id']}/revoke",
        headers=auth(other_device["credential"]),
    )
    revoked = harness.client.post(
        f"/v1/machines/{machine['machine_id']}/revoke",
        headers=auth(device["credential"]),
    )

    assert denied.status_code == 404
    assert denied.json()["detail"]["code"] == "machine_not_found"
    assert revoked.status_code == 204
    assert (
        harness.client.put(
            f"/v1/runs/{run_id}",
            headers=auth(machine["credential"]),
            json={"machine_id": machine["machine_id"], "title": "Rejected"},
        ).status_code
        == 401
    )
    read = harness.client.get(f"/v1/runs/{run_id}", headers=auth(device["credential"]))
    assert read.status_code == 200
    with harness.session_factory() as session:
        machine_row = session.get(Machine, machine["machine_id"])
        assert machine_row is not None and machine_row.revoked_at is not None
        assert (
            session.scalar(
                select(func.count())
                .select_from(MachineDeviceSubscription)
                .where(MachineDeviceSubscription.machine_id == machine["machine_id"])
            )
            == 0
        )
        outbox = session.get(PushOutbox, "out_pending_lifecycle")
        assert outbox is not None and outbox.status == "cancelled"


def test_machine_revoke_self_is_scoped_and_can_repair_same_workspace(harness: Harness) -> None:
    device, machine = harness.pair()
    wrong_id = harness.client.post(
        "/v1/machines/not-self/revoke-self",
        headers=auth(machine["credential"]),
    )
    revoked = harness.client.post(
        f"/v1/machines/{machine['machine_id']}/revoke-self",
        headers=auth(machine["credential"]),
    )
    assert wrong_id.status_code == 403
    assert wrong_id.json()["detail"]["code"] == "machine_ownership_mismatch"
    assert revoked.status_code == 204
    assert (
        harness.client.get("/v1/machines", headers=auth(machine["credential"])).status_code == 401
    )

    created = harness.client.post(
        "/v1/pairing-sessions",
        json={"machine_id": machine["machine_id"], "display_name": "Repaired"},
    ).json()
    claimed = harness.client.post(
        f"/v1/pairing-sessions/{created['pairing_session_id']}/claim",
        headers=auth(device["credential"]),
        json={"challenge": created["challenge"]},
    )
    assert claimed.status_code == 200, claimed.text


def test_reset_device_revokes_identity_tokens_bindings_subscriptions_and_pending_push(
    harness: Harness,
) -> None:
    device, machine = harness.pair()
    run_id = "10000000-0000-4000-8000-000000000003"
    harness.register_run(machine, run_id)
    assert (
        harness.client.put(
            f"/v1/devices/{device['device_id']}/notification-token",
            headers=auth(device["credential"]),
            json={"token": "notification-token"},
        ).status_code
        == 204
    )
    with harness.session_factory() as session:
        session.add(
            LiveActivityBinding(
                id="lab_device_reset",
                run_id=run_id,
                device_id=device["device_id"],
                activity_id="activity-reset",
                state="active",
                update_push_token_encrypted="encrypted",
            )
        )
        session.add(
            PushOutbox(
                id="out_device_reset",
                kind="LIVE_UPDATE",
                target_type="activity",
                target_id="lab_device_reset",
                run_id=run_id,
                desired_payload={"aps": {}},
                status="pending",
                coalesce_key=f"live:{run_id}:{device['device_id']}",
            )
        )
        session.commit()

    denied = harness.client.delete(
        "/v1/devices/not-self",
        headers=auth(device["credential"]),
    )
    reset = harness.client.delete(
        f"/v1/devices/{device['device_id']}",
        headers=auth(device["credential"]),
    )

    assert denied.status_code == 403
    assert reset.status_code == 204
    assert harness.client.get("/v1/runs", headers=auth(device["credential"])).status_code == 401
    with harness.session_factory() as session:
        stored = session.get(Device, device["device_id"])
        assert stored is not None
        assert stored.notification_token_encrypted is None
        assert stored.push_to_start_token_encrypted is None
        credential = session.scalar(
            select(DeviceCredential).where(DeviceCredential.device_id == device["device_id"])
        )
        assert credential is not None and credential.revoked_at is not None
        binding = session.get(LiveActivityBinding, "lab_device_reset")
        assert binding is not None and binding.state == "invalidated"
        assert binding.update_push_token_encrypted is None
        outbox = session.get(PushOutbox, "out_device_reset")
        assert outbox is not None and outbox.status == "cancelled"


def test_workspace_deletion_challenge_rotation_expiry_and_cross_workspace(
    harness: Harness,
) -> None:
    device, _machine = pair_named(
        harness,
        installation_id="ios-delete-owner",
        machine_id="machine-delete-owner",
    )
    other_device, _ = pair_named(
        harness,
        installation_id="ios-delete-other",
        machine_id="machine-delete-other",
    )
    workspace_id = device["workspace_id"]
    wrong_confirmation = harness.client.post(
        f"/v1/workspaces/{workspace_id}/deletion-challenge",
        headers=auth(device["credential"]),
        json={"confirmation": "delete"},
    )
    cross_workspace = harness.client.post(
        f"/v1/workspaces/{workspace_id}/deletion-challenge",
        headers=auth(other_device["credential"]),
        json={"confirmation": "DELETE"},
    )
    first = harness.client.post(
        f"/v1/workspaces/{workspace_id}/deletion-challenge",
        headers=auth(device["credential"]),
        json={"confirmation": "DELETE"},
    ).json()
    second = harness.client.post(
        f"/v1/workspaces/{workspace_id}/deletion-challenge",
        headers=auth(device["credential"]),
        json={"confirmation": "DELETE"},
    ).json()
    rotated = harness.client.request(
        "DELETE",
        f"/v1/workspaces/{workspace_id}",
        headers=auth(device["credential"]),
        json={"challenge": first["challenge"]},
    )
    with harness.session_factory() as session:
        challenge = session.scalar(
            select(WorkspaceDeletionChallenge).where(
                WorkspaceDeletionChallenge.workspace_id == workspace_id
            )
        )
        assert challenge is not None
        challenge.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    expired = harness.client.request(
        "DELETE",
        f"/v1/workspaces/{workspace_id}",
        headers=auth(device["credential"]),
        json={"challenge": second["challenge"]},
    )

    assert wrong_confirmation.status_code == 409
    assert wrong_confirmation.json()["detail"]["code"] == "confirmation_mismatch"
    assert cross_workspace.status_code == 404
    assert rotated.status_code == 409
    assert rotated.json()["detail"]["code"] == "invalid_deletion_challenge"
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "expired_deletion_challenge"


def test_workspace_deletion_removes_all_workspace_data_and_bearers(harness: Harness) -> None:
    device, machine = harness.pair()
    run_id = "10000000-0000-4000-8000-000000000004"
    harness.register_run(machine, run_id)
    with harness.session_factory() as session:
        now = datetime.now(UTC)
        session.add(
            Notification(
                id="ntf_workspace_delete",
                workspace_id=device["workspace_id"],
                machine_id=machine["machine_id"],
                run_id=run_id,
                title="Delete",
                body="Delete",
                level="info",
            )
        )
        session.add(
            PushOutbox(
                id="out_workspace_delete",
                kind="LIVE_START",
                target_type="device",
                target_id=device["device_id"],
                run_id=run_id,
                desired_payload={"aps": {}},
                status="sent",
                coalesce_key="delete-workspace",
            )
        )
        session.add_all(
            [
                RateLimitBucket(
                    bucket_name="notification_daily_quota",
                    subject_key=anonymized_key(
                        harness.settings, "workspace", device["workspace_id"]
                    ),
                    window_start=1,
                    request_count=1,
                    expires_at=now + timedelta(hours=1),
                    updated_at=now,
                ),
                RateLimitBucket(
                    bucket_name="event_batch",
                    subject_key=anonymized_key(harness.settings, "machine", machine["machine_id"]),
                    window_start=1,
                    request_count=1,
                    expires_at=now + timedelta(hours=1),
                    updated_at=now,
                ),
            ]
        )
        session.flush()
        session.add(
            PushAttempt(
                id="pat_workspace_delete",
                outbox_id="out_workspace_delete",
                status_code=200,
                request_payload={"aps": {}},
                request_headers={},
            )
        )
        session.commit()
    challenge = harness.client.post(
        f"/v1/workspaces/{device['workspace_id']}/deletion-challenge",
        headers=auth(device["credential"]),
        json={"confirmation": "DELETE"},
    ).json()["challenge"]

    deleted = harness.client.request(
        "DELETE",
        f"/v1/workspaces/{device['workspace_id']}",
        headers=auth(device["credential"]),
        json={"challenge": challenge},
    )

    assert deleted.status_code == 204, deleted.text
    assert harness.client.get("/v1/runs", headers=auth(device["credential"])).status_code == 401
    assert (
        harness.client.put(
            f"/v1/runs/{run_id}",
            headers=auth(machine["credential"]),
            json={"machine_id": machine["machine_id"], "title": "Rejected"},
        ).status_code
        == 401
    )
    with harness.session_factory() as session:
        assert session.get(Workspace, device["workspace_id"]) is None
        assert session.get(Device, device["device_id"]) is None
        assert session.get(Machine, machine["machine_id"]) is None
        assert session.get(Run, run_id) is None
        assert session.get(Notification, "ntf_workspace_delete") is None
        assert session.get(PushOutbox, "out_workspace_delete") is None
        assert session.get(PushAttempt, "pat_workspace_delete") is None
        identifiable_rate_keys = {
            anonymized_key(harness.settings, "workspace", device["workspace_id"]),
            anonymized_key(harness.settings, "machine", machine["machine_id"]),
        }
        assert (
            session.scalar(
                select(func.count())
                .select_from(RateLimitBucket)
                .where(RateLimitBucket.subject_key.in_(identifiable_rate_keys))
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(QuotaLock)) == 1
        remaining_lock = session.scalar(select(QuotaLock))
        assert remaining_lock is not None
        assert remaining_lock.lock_key.startswith("pending_pairings:")
        assert (
            session.scalar(select(AuditLog).where(AuditLog.workspace_id == device["workspace_id"]))
            is None
        )


def test_workspace_deletion_rolls_back_as_one_transaction(
    harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import lifecycle

    device, machine = harness.pair()
    challenge = harness.client.post(
        f"/v1/workspaces/{device['workspace_id']}/deletion-challenge",
        headers=auth(device["credential"]),
        json={"confirmation": "DELETE"},
    ).json()["challenge"]

    def fail_after_partial_delete(session: Any, _settings: Any, workspace_id: str) -> None:
        session.execute(
            # A forced exception after a write verifies the request-scoped transaction rolls back.
            __import__("sqlalchemy")
            .delete(Notification)
            .where(Notification.workspace_id == workspace_id)
        )
        raise RuntimeError("forced deletion failure")

    monkeypatch.setattr(lifecycle, "_delete_workspace_rows", fail_after_partial_delete)
    with pytest.raises(RuntimeError, match="forced deletion failure"):
        harness.client.request(
            "DELETE",
            f"/v1/workspaces/{device['workspace_id']}",
            headers=auth(device["credential"]),
            json={"challenge": challenge},
        )

    with harness.session_factory() as session:
        assert session.get(Workspace, device["workspace_id"]) is not None
        credential = session.scalar(
            select(MachineCredential).where(MachineCredential.machine_id == machine["machine_id"])
        )
        assert credential is not None and credential.revoked_at is None
