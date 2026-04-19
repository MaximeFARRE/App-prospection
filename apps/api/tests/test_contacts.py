from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.campaign_state import CampaignState
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
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
