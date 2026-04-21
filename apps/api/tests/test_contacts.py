from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models.campaign_state import CampaignState
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
from app.repositories import contact_repository
from app.services.eligibility_service import check_eligibility


def test_contact_blocked_is_denied(db: Session) -> None:
    contact = _create_contact(db, email="blocked@example.com", is_blocked=True)
    result = check_eligibility(contact, db, "camp1")

    assert result.eligible is False
    assert result.reason == "blocked"
    assert result.next_step is None


def test_contact_without_history_is_intro_eligible(db: Session) -> None:
    contact = _create_contact(db, email="new@example.com")
    result = check_eligibility(contact, db, "camp1")

    assert result.eligible is True
    assert result.reason == "ok"
    assert result.next_step == "intro"


def test_contact_with_prior_message_is_denied_as_already_sent(db: Session) -> None:
    contact = _create_contact(db, email="already-sent@example.com")
    db.add(
        Message(
            contact_id=contact.id,
            campaign_name="old-campaign",
            subject="Hello",
            body="Body",
            from_email="sender@example.com",
            message_type="intro",
            gmail_message_id="gmail-1",
            sent_at=_utcnow_naive(),
        )
    )
    db.commit()

    result = check_eligibility(contact, db, "camp1")
    assert result.eligible is False
    assert result.reason == "already_sent"


def test_followup_delay_not_reached_is_denied(db: Session) -> None:
    contact = _create_contact(db, email="delay@example.com")
    db.add(
        CampaignState(
            contact_id=contact.id,
            campaign_name="camp1",
            intro_sent=True,
            intro_sent_at=_utcnow_naive() - timedelta(days=1),
        )
    )
    db.commit()

    result = check_eligibility(contact, db, "camp1")
    assert result.eligible is False
    assert result.reason == "delay_not_reached"


def test_followup_after_seven_days_is_eligible(db: Session) -> None:
    contact = _create_contact(db, email="followup@example.com")
    db.add(
        CampaignState(
            contact_id=contact.id,
            campaign_name="camp1",
            intro_sent=True,
            intro_sent_at=_utcnow_naive() - timedelta(days=8),
        )
    )
    db.commit()

    result = check_eligibility(contact, db, "camp1")
    assert result.eligible is True
    assert result.reason == "ok"
    assert result.next_step == "followup_1"


def test_contact_with_reply_is_denied(db: Session) -> None:
    contact = _create_contact(db, email="replied@example.com")
    db.add(
        Reply(
            contact_id=contact.id,
            in_reply_to_message_id=None,
            subject="Re: hello",
            body="Thanks",
            from_email="replied@example.com",
            gmail_thread_id="thread-1",
            sentiment="neutral",
            received_at=_utcnow_naive(),
        )
    )
    db.commit()

    result = check_eligibility(contact, db, "camp1")
    assert result.eligible is False
    assert result.reason == "replied"


def test_contacts_repository_marks_contacted_status_from_messages(db: Session) -> None:
    contacted = _create_contact(db, email="contacted@example.com")
    new_contact = _create_contact(db, email="new-contact@example.com")
    db.add(
        Message(
            contact_id=contacted.id,
            campaign_name=None,
            subject="historical",
            body="historical",
            from_email="sender@example.com",
            message_type="historical",
            gmail_message_id="gmail-historical-1",
            sent_at=_utcnow_naive(),
        )
    )
    db.commit()

    contacts = contact_repository.get_all(db, {"page": 1, "page_size": 100})
    by_id = {contact.id: contact for contact in contacts}

    assert bool(getattr(by_id[contacted.id], "has_been_contacted", False)) is True
    assert bool(getattr(by_id[new_contact.id], "has_been_contacted", False)) is False


def test_contacts_repository_filters_contacted_status(db: Session) -> None:
    contacted = _create_contact(db, email="only-contacted@example.com")
    not_contacted = _create_contact(db, email="only-not-contacted@example.com")
    db.add(
        Message(
            contact_id=contacted.id,
            campaign_name=None,
            subject="historical",
            body="historical",
            from_email="sender@example.com",
            message_type="historical",
            gmail_message_id="gmail-historical-2",
            sent_at=_utcnow_naive(),
        )
    )
    db.commit()

    contacted_rows = contact_repository.get_all(db, {"page": 1, "page_size": 100, "contacted": "contacted"})
    not_contacted_rows = contact_repository.get_all(
        db,
        {"page": 1, "page_size": 100, "contacted": "not_contacted"},
    )

    contacted_ids = {row.id for row in contacted_rows}
    not_contacted_ids = {row.id for row in not_contacted_rows}

    assert contacted.id in contacted_ids
    assert not_contacted.id not in contacted_ids
    assert not_contacted.id in not_contacted_ids
    assert contacted.id not in not_contacted_ids


def test_contacts_repository_set_names_updates_first_and_last_name(db: Session) -> None:
    contact = _create_contact(db, email="rename@example.com")

    updated = contact_repository.set_names(
        db,
        contact_id=contact.id,
        first_name="  Maxime  ",
        last_name="  Farre  ",
    )
    db.commit()
    assert updated is not None
    assert updated.first_name == "Maxime"
    assert updated.last_name == "Farre"

    updated = contact_repository.set_names(
        db,
        contact_id=contact.id,
        first_name="",
        last_name="   ",
    )
    db.commit()
    assert updated is not None
    assert updated.first_name is None
    assert updated.last_name is None


def test_contacts_repository_set_blocked_updates_status(db: Session) -> None:
    contact = _create_contact(db, email="blockme@example.com", is_blocked=False)

    updated = contact_repository.set_blocked(db, contact_id=contact.id, is_blocked=True)
    db.commit()

    assert updated is not None
    assert updated.is_blocked is True


def test_contacts_repository_create_manual_contact_creates_company_and_contact(db: Session) -> None:
    created = contact_repository.create_manual_contact(
        db,
        first_name=" Maxime ",
        last_name=" Farre ",
        email="Maxime.Farre@example.com",
        company_name="Acme",
        job_title="Analyst",
        sex="male",
        country="France",
        city="Paris",
        phone="0600000000",
        linkedin_url="https://linkedin.com/in/maxime",
        notes="Ajout manuel",
    )
    db.commit()

    assert created.id is not None
    assert created.first_name == "Maxime"
    assert created.last_name == "Farre"
    assert created.sex == "homme"
    assert created.email == "Maxime.Farre@example.com"
    assert created.email_normalized == "maxime.farre@example.com"
    assert created.company_id is not None
    assert created.source == "manual"

    stored_company = getattr(created, "company", None)
    assert stored_company is not None
    assert stored_company.name == "Acme"


def test_contacts_repository_create_manual_contact_rejects_duplicate_email(db: Session) -> None:
    _create_contact(db, email="alice@example.com")

    with pytest.raises(ValueError, match="existe déjà"):
        contact_repository.create_manual_contact(
            db,
            first_name="Alice",
            last_name="Martin",
            email="ALICE@EXAMPLE.COM",
            company_name="Acme",
        )


def _create_contact(db: Session, email: str, is_blocked: bool = False) -> Contact:
    contact = Contact(
        first_name="Alice",
        last_name="Martin",
        email=email,
        email_normalized=email,
        is_blocked=is_blocked,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
