from __future__ import annotations

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
