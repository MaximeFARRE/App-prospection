from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

import app.services.campaign_prepare_service as campaign_prepare_service
from app.core.config import GmailAccount
from app.models.company import Company
from app.models.contact import Contact
from app.models.message import Message
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
        _queued_email(contact_id=4, email="third@orange.fr"),
        _queued_email(contact_id=5, email="third@outlook.com"),
        _queued_email(contact_id=6, email="pro2@another-corp.io"),
        _queued_email(contact_id=7, email="fourth@wanadoo.fr"),
        _queued_email(contact_id=8, email="fifth@free.fr"),
    ]

    prioritized = _prioritize_business_emails(queue)

    assert [item.contact.id for item in prioritized] == [2, 6, 1, 3, 4, 5, 7, 8]


def test_is_personal_email_detects_common_personal_domains_case_insensitive() -> None:
    assert _is_personal_email("Person@GMAIL.com") is True
    assert _is_personal_email("person@outlook.com") is True
    assert _is_personal_email("person@yahoo.com") is True
    assert _is_personal_email("person@hotmail.fr") is True
    assert _is_personal_email("person@orange.fr") is True
    assert _is_personal_email("person@wanadoo.fr") is True
    assert _is_personal_email("person@free.fr") is True
    assert _is_personal_email("person@company.com") is False


def test_prepare_campaign_limits_same_company_within_single_queue(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_campaign_test_runtime(monkeypatch, weekly_limit=3)
    company = Company(name="Acme")
    db.add(company)
    db.commit()
    db.refresh(company)

    for index in range(6):
        db.add(
            Contact(
                first_name=f"User{index}",
                last_name="Queue",
                sex="homme",
                email=f"user{index}@acme.example",
                email_normalized=f"user{index}@acme.example",
                company_id=company.id,
                country="France",
                is_blocked=False,
            )
        )
    db.commit()

    result = campaign_prepare_service.prepare_campaign("campagne-test", db, dry_run=True)

    assert len(result.queue) == 3
    assert all(item.contact.company_id == company.id for item in result.queue)
    assert sum(1 for item in result.skipped if item.reason == "company_weekly_limit") == 3


def test_prepare_campaign_counts_existing_weekly_messages_for_company_limit(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_campaign_test_runtime(monkeypatch, weekly_limit=3)
    company = Company(name="AlreadyCounted Inc")
    db.add(company)
    db.commit()
    db.refresh(company)

    old_contacts: list[Contact] = []
    for index in range(2):
        contact = Contact(
            first_name=f"Sent{index}",
            last_name="History",
            sex="homme",
            email=f"sent{index}@history.example",
            email_normalized=f"sent{index}@history.example",
            company_id=company.id,
            country="France",
            is_blocked=False,
        )
        db.add(contact)
        old_contacts.append(contact)

    for index in range(2):
        db.add(
            Contact(
                first_name=f"New{index}",
                last_name="History",
                sex="homme",
                email=f"new{index}@history.example",
                email_normalized=f"new{index}@history.example",
                company_id=company.id,
                country="France",
                is_blocked=False,
            )
        )
    db.commit()

    for index, contact in enumerate(old_contacts):
        db.add(
            Message(
                contact_id=contact.id,
                campaign_name="old-campaign",
                subject=f"Old subject {index}",
                body="Old body",
                from_email="sender@example.com",
                message_type="intro",
                gmail_message_id=f"gmail-old-{index}",
                sent_at=datetime.utcnow(),
            )
        )
    db.commit()

    result = campaign_prepare_service.prepare_campaign("campagne-test", db, dry_run=True)

    assert len(result.queue) == 1
    assert sum(1 for item in result.skipped if item.reason == "already_sent") == 2
    assert sum(1 for item in result.skipped if item.reason == "company_weekly_limit") == 1


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


def _configure_campaign_test_runtime(
    monkeypatch: pytest.MonkeyPatch,
    weekly_limit: int,
) -> None:
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_client_id_1", "id")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_client_secret_1", "secret")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_refresh_token_1", "refresh")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_email_1", "sender@example.com")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_client_id_2", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_client_secret_2", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_refresh_token_2", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_email_2", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_client_id_3", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_client_secret_3", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_refresh_token_3", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "gmail_email_3", "")
    monkeypatch.setattr(campaign_prepare_service.settings, "company_weekly_send_limit", weekly_limit)
    monkeypatch.setattr(campaign_prepare_service, "detect_language", lambda _contact: "fr")
    monkeypatch.setattr(campaign_prepare_service, "render_for_contact", _fake_render_for_contact)


def _fake_render_for_contact(
    step: str,
    contact: Contact,
    _account: GmailAccount,
    position: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        subject=f"{step}-{contact.id}-{position}",
        body="<p>body</p>",
        language="fr",
        ab_variant="a",
    )
