from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .apns import (
    APNsProvider,
    APNsRequest,
    live_activity_headers,
    normal_notification_headers,
)
from .config import Settings
from .models import (
    Device,
    LiveActivityBinding,
    PushAttempt,
    PushOutbox,
    utcnow,
)
from .security import TokenCipher, new_id


class OutboxProcessor:
    def __init__(
        self,
        settings: Settings,
        provider: APNsProvider,
        cipher: TokenCipher,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.cipher = cipher

    def _request_for(self, session: Session, item: PushOutbox) -> APNsRequest | None:
        if item.target_type == "device":
            device = session.get(Device, item.target_id)
            if device is None or device.revoked_at is not None:
                return None
            encrypted = (
                device.push_to_start_token_encrypted
                if item.kind == "LIVE_START"
                else device.notification_token_encrypted
            )
            if encrypted is None:
                return None
            token = self.cipher.decrypt(encrypted)
        else:
            binding = session.get(LiveActivityBinding, item.target_id)
            if (
                binding is None
                or binding.invalidated_at is not None
                or binding.update_push_token_encrypted is None
            ):
                return None
            token = self.cipher.decrypt(binding.update_push_token_encrypted)

        if item.kind == "NOTIFICATION":
            headers = normal_notification_headers(self.settings, item.priority)
        else:
            headers = live_activity_headers(
                self.settings,
                item.priority,
                collapse_id=f"{item.run_id}:{item.target_id}" if item.run_id else None,
            )
        return APNsRequest(token=token, payload=item.desired_payload, headers=headers)

    def _has_live_activity_capacity(self, session: Session, item: PushOutbox) -> bool:
        if item.kind != "LIVE_START":
            return True
        count = session.scalar(
            select(func.count())
            .select_from(LiveActivityBinding)
            .where(
                LiveActivityBinding.device_id == item.target_id,
                LiveActivityBinding.state == "active",
                LiveActivityBinding.invalidated_at.is_(None),
            )
        )
        return int(count or 0) < self.settings.live_activity_max_per_device

    def process_one(self, session: Session) -> bool:
        now = utcnow()
        item = session.scalar(
            select(PushOutbox)
            .where(
                PushOutbox.status == "pending",
                PushOutbox.available_at <= now,
            )
            .order_by(PushOutbox.priority.desc(), PushOutbox.available_at, PushOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if item is None:
            return False
        if not self._has_live_activity_capacity(session, item):
            item.status = "suppressed"
            item.last_error = "per-device Live Activity limit reached"
            item.updated_at = now
            session.commit()
            return True
        request = self._request_for(session, item)
        if request is None:
            item.status = "cancelled"
            item.last_error = "target token unavailable"
            item.updated_at = now
            session.commit()
            return True

        result = self.provider.send(request)
        item.attempt_count += 1
        session.add(
            PushAttempt(
                id=new_id("pat"),
                outbox_id=item.id,
                status_code=result.status_code,
                apns_id=result.apns_id,
                reason=result.reason,
                request_payload=request.payload,
                request_headers=request.headers,
            )
        )
        if result.accepted:
            item.status = "sent"
            if item.kind == "LIVE_START" and item.run_id is not None:
                session.add(
                    LiveActivityBinding(
                        id=new_id("lab"),
                        run_id=item.run_id,
                        device_id=item.target_id,
                        activity_id=f"pending:{item.id}",
                        state="active",
                    )
                )
            if item.kind == "LIVE_END":
                binding = session.get(LiveActivityBinding, item.target_id)
                if binding is not None:
                    binding.state = "ended"
                    binding.ended_at = now
        elif result.invalid_token:
            item.status = "failed"
            item.last_error = result.reason or f"APNs {result.status_code}"
            if item.target_type == "device":
                device = session.get(Device, item.target_id)
                if device is not None:
                    if item.kind == "LIVE_START":
                        device.push_to_start_token_encrypted = None
                    else:
                        device.notification_token_encrypted = None
            else:
                binding = session.get(LiveActivityBinding, item.target_id)
                if binding is not None:
                    binding.invalidated_at = now
                    binding.state = "invalidated"
                    binding.update_push_token_encrypted = None
        elif result.retryable and item.attempt_count < self.settings.outbox_max_attempts:
            item.status = "pending"
            item.available_at = now + timedelta(seconds=min(300, 2 ** min(item.attempt_count, 8)))
            item.last_error = result.reason or f"APNs {result.status_code}"
        else:
            item.status = "failed"
            item.last_error = result.reason or f"APNs {result.status_code}"
        item.updated_at = now
        session.commit()
        return True

    def drain(self, session: Session, limit: int = 100) -> int:
        processed = 0
        while processed < limit and self.process_one(session):
            processed += 1
        return processed
