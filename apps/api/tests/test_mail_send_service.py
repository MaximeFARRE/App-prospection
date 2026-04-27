from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.config import GmailAccount
from app.models.contact import Contact
from app.services.campaign_prepare_service import QueuedEmail
from app.services.email_verification_service import EmailVerificationDecision
from app.services import send_queue_verification_service


def test_apply_email_verification_gate_removes_unverified_and_bypasses_after_limit() -> None:
    queue = [
        _queued_email(contact_id=1, email="invalid@example.com"),
        _queued_email(contact_id=2, email="limit@example.com"),
        _queued_email(contact_id=3, email="after-limit@example.com"),
    ]
    calls: list[str] = []

    def _fake_verify(email: str) -> EmailVerificationDecision:
        calls.append(email)
        if email == "invalid@example.com":
            return EmailVerificationDecision(
                can_send=False,
                api_limit_reached=False,
                reason="safe_to_send_false",
                provider_result="invalid",
            )
        if email == "limit@example.com":
            return EmailVerificationDecision(
                can_send=True,
                api_limit_reached=True,
                reason="api_limit_status_402",
            )
        return EmailVerificationDecision(
            can_send=True,
            api_limit_reached=False,
            reason="safe_to_send_true",
            provider_result="valid",
        )

    original_verify = send_queue_verification_service.verify_email_for_send
    send_queue_verification_service.verify_email_for_send = _fake_verify
    try:
        filtered, removed = send_queue_verification_service.filter_send_queue_with_email_verification(queue)
    finally:
        send_queue_verification_service.verify_email_for_send = original_verify

    assert removed == 1
    assert [item.contact.id for item in filtered] == [2, 3]
    # Le 3e n'est pas vérifié car la limite API est atteinte sur le 2e
    assert calls == ["invalid@example.com", "limit@example.com"]


def test_should_send_item_with_email_verification_allows_send_on_qev_http_error() -> None:
    item = _queued_email(contact_id=1, email="error@example.com")

    def _fake_verify(_email: str) -> EmailVerificationDecision:
        return EmailVerificationDecision(
            can_send=False,
            api_limit_reached=False,
            reason="http_error:ReadTimeout",
        )

    original_verify = send_queue_verification_service.verify_email_for_send
    send_queue_verification_service.verify_email_for_send = _fake_verify
    try:
        should_send, api_limit_reached, reason = (
            send_queue_verification_service.should_send_item_with_email_verification(
                item,
                decision_cache={},
                api_limit_reached=False,
            )
        )
    finally:
        send_queue_verification_service.verify_email_for_send = original_verify

    assert should_send is True
    assert api_limit_reached is False
    assert reason == "http_error:ReadTimeout"
    assert item.contact.email_status == "unknown"
    assert item.contact.email_check_reason == "http_error:ReadTimeout"
    assert item.contact.email_checked_at is not None


def test_should_send_item_with_email_verification_skips_invalid_before_limit() -> None:
    item = _queued_email(contact_id=2, email="invalid@example.com")

    def _fake_verify(_email: str) -> EmailVerificationDecision:
        return EmailVerificationDecision(
            can_send=False,
            api_limit_reached=False,
            reason="safe_to_send_false",
            provider_result="invalid",
        )

    original_verify = send_queue_verification_service.verify_email_for_send
    send_queue_verification_service.verify_email_for_send = _fake_verify
    try:
        should_send, api_limit_reached, reason = (
            send_queue_verification_service.should_send_item_with_email_verification(
                item,
                decision_cache={},
                api_limit_reached=False,
            )
        )
    finally:
        send_queue_verification_service.verify_email_for_send = original_verify

    assert should_send is False
    assert api_limit_reached is False
    assert reason == "safe_to_send_false"
    assert item.contact.email_status == "invalid"
    assert item.contact.email_check_reason == "safe_to_send_false"
    assert item.contact.email_checked_at is not None


def test_should_send_item_with_email_verification_uses_fresh_cached_invalid_status() -> None:
    item = _queued_email(contact_id=3, email="cached-invalid@example.com")
    item.contact.email_status = "invalid"
    item.contact.email_checked_at = _utcnow_naive() - timedelta(days=1)
    item.contact.email_check_reason = "cached_status_invalid"
    calls: list[str] = []

    def _fake_verify(email: str) -> EmailVerificationDecision:
        calls.append(email)
        return EmailVerificationDecision(
            can_send=True,
            api_limit_reached=False,
            reason="safe_to_send_true",
            provider_result="valid",
        )

    original_ttl = send_queue_verification_service.settings.email_verification_ttl_days
    original_verify = send_queue_verification_service.verify_email_for_send
    send_queue_verification_service.settings.email_verification_ttl_days = 30
    send_queue_verification_service.verify_email_for_send = _fake_verify
    try:
        should_send, api_limit_reached, reason = (
            send_queue_verification_service.should_send_item_with_email_verification(
                item,
                decision_cache={},
                api_limit_reached=False,
            )
        )
    finally:
        send_queue_verification_service.settings.email_verification_ttl_days = original_ttl
        send_queue_verification_service.verify_email_for_send = original_verify

    assert should_send is False
    assert api_limit_reached is False
    assert reason == "cached_status_invalid"
    assert calls == []


def test_should_send_item_with_email_verification_refreshes_expired_status() -> None:
    item = _queued_email(contact_id=4, email="expired-status@example.com")
    item.contact.email_status = "invalid"
    item.contact.email_checked_at = _utcnow_naive() - timedelta(days=45)
    item.contact.email_check_reason = "old_invalid_status"
    calls: list[str] = []

    def _fake_verify(email: str) -> EmailVerificationDecision:
        calls.append(email)
        return EmailVerificationDecision(
            can_send=True,
            api_limit_reached=False,
            reason="safe_to_send_true",
            provider_result="valid",
        )

    original_ttl = send_queue_verification_service.settings.email_verification_ttl_days
    original_verify = send_queue_verification_service.verify_email_for_send
    send_queue_verification_service.settings.email_verification_ttl_days = 30
    send_queue_verification_service.verify_email_for_send = _fake_verify
    try:
        should_send, api_limit_reached, reason = (
            send_queue_verification_service.should_send_item_with_email_verification(
                item,
                decision_cache={},
                api_limit_reached=False,
            )
        )
    finally:
        send_queue_verification_service.settings.email_verification_ttl_days = original_ttl
        send_queue_verification_service.verify_email_for_send = original_verify

    assert should_send is True
    assert api_limit_reached is False
    assert reason == "safe_to_send_true"
    assert calls == ["expired-status@example.com"]
    assert item.contact.email_status == "valid"
    assert item.contact.email_check_reason == "safe_to_send_true"
    assert item.contact.email_checked_at is not None


def test_should_send_item_with_email_verification_marks_unknown_when_verification_disabled() -> None:
    item = _queued_email(contact_id=5, email="disabled@example.com")

    def _fake_verify(_email: str) -> EmailVerificationDecision:
        return EmailVerificationDecision(
            can_send=True,
            api_limit_reached=False,
            reason="verification_disabled_missing_api_key",
        )

    original_verify = send_queue_verification_service.verify_email_for_send
    send_queue_verification_service.verify_email_for_send = _fake_verify
    try:
        should_send, api_limit_reached, reason = (
            send_queue_verification_service.should_send_item_with_email_verification(
                item,
                decision_cache={},
                api_limit_reached=False,
            )
        )
    finally:
        send_queue_verification_service.verify_email_for_send = original_verify

    assert should_send is True
    assert api_limit_reached is False
    assert reason == "verification_disabled_missing_api_key"
    assert item.contact.email_status == "unknown"
    assert item.contact.email_check_reason == "verification_disabled_missing_api_key"
    assert item.contact.email_checked_at is not None


def _queued_email(contact_id: int, email: str) -> QueuedEmail:
    contact = Contact(
        first_name=f"User{contact_id}",
        last_name="Test",
        email=email,
        email_normalized=email,
    )
    contact.id = contact_id

    account = GmailAccount(
        client_id="id",
        client_secret="secret",
        refresh_token="refresh",
        email="sender@example.com",
    )
    return QueuedEmail(
        contact=contact,
        account=account,
        step="intro",
        subject="subject",
        body="<p>body</p>",
        language="fr",
        ab_variant="a",
    )


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
