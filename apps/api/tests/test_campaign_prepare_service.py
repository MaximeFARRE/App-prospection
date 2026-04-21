from __future__ import annotations

from app.core.config import GmailAccount
from app.models.contact import Contact
from app.services.campaign_prepare_service import (
    QueuedEmail,
    _is_personal_email,
    _prioritize_business_emails,
)


def test_prioritize_business_emails_moves_personal_domains_to_end() -> None:
    queue = [
        _queued_email(contact_id=1, email="first@gmail.com"),
        _queued_email(contact_id=2, email="pro1@company.com"),
        _queued_email(contact_id=3, email="second@yahoo.com"),
        _queued_email(contact_id=4, email="pro2@another-corp.io"),
        _queued_email(contact_id=5, email="third@outlook.com"),
    ]

    prioritized = _prioritize_business_emails(queue)

    assert [item.contact.id for item in prioritized] == [2, 4, 1, 3, 5]


def test_is_personal_email_detects_common_personal_domains_case_insensitive() -> None:
    assert _is_personal_email("Person@GMAIL.com") is True
    assert _is_personal_email("person@outlook.com") is True
    assert _is_personal_email("person@yahoo.com") is True
    assert _is_personal_email("person@company.com") is False


def _queued_email(contact_id: int, email: str) -> QueuedEmail:
    contact = Contact(
        first_name=f"User{contact_id}",
        last_name="Test",
        email=email,
        email_normalized=email.lower(),
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
