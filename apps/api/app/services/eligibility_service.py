from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.campaign_state import CampaignState
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
from app.utils.email_normalization import is_valid_email


FOLLOWUP_WAIT = timedelta(days=7)
SEND_TYPES = ("intro", "followup_1", "followup_2")


@dataclass(slots=True)
class EligibilityResult:
    contact_id: int
    eligible: bool
    reason: str
    next_step: str | None


def check_eligibility(contact: Contact, db: Session, campaign_name: str) -> EligibilityResult:
    now = datetime.utcnow()

    if _is_email_missing(contact):
        return _deny(contact.id, "no_email")

    if not is_valid_email(contact.email):
        return _deny(contact.id, "invalid_email")

    if bool(contact.is_blocked):
        return _deny(contact.id, "blocked")

    if _has_reply(contact.id, db):
        return _deny(contact.id, "replied")

    if _company_weekly_limit_reached(contact, db):
        return _deny(contact.id, "company_weekly_limit")

    campaign_state = _get_campaign_state(contact.id, campaign_name, db)
    if campaign_state is None and _has_prior_sent_message(contact.id, db):
        return _deny(contact.id, "already_sent")

    next_step, last_sent_at, sequence_complete = _resolve_next_step(campaign_state)
    if sequence_complete:
        return _deny(contact.id, "sequence_complete")

    if _delay_not_reached(last_sent_at, now, next_step):
        return _deny(contact.id, "delay_not_reached")

    return EligibilityResult(
        contact_id=contact.id,
        eligible=True,
        reason="ok",
        next_step=next_step,
    )


def bulk_check(contacts: list[Contact], db: Session, campaign_name: str) -> list[EligibilityResult]:
    return [check_eligibility(contact, db, campaign_name) for contact in contacts]


def _deny(contact_id: int, reason: str) -> EligibilityResult:
    return EligibilityResult(
        contact_id=contact_id,
        eligible=False,
        reason=reason,
        next_step=None,
    )


def _is_email_missing(contact: Contact) -> bool:
    if contact.email is None:
        return True
    return not contact.email.strip()


def _has_reply(contact_id: int, db: Session) -> bool:
    return (
        db.query(Reply.id)
        .filter(Reply.contact_id == contact_id)
        .limit(1)
        .first()
        is not None
    )


def _get_campaign_state(contact_id: int, campaign_name: str, db: Session) -> CampaignState | None:
    return (
        db.query(CampaignState)
        .filter(
            CampaignState.contact_id == contact_id,
            CampaignState.campaign_name == campaign_name,
        )
        .first()
    )


def _company_weekly_limit_reached(contact: Contact, db: Session) -> bool:
    """Vrai si l'entreprise du contact a déjà reçu trop de mails cette semaine."""
    limit = int(settings.company_weekly_send_limit)
    if limit <= 0:
        return False
    company_id = getattr(contact, "company_id", None)
    if not company_id:
        return False
    week_start = datetime.utcnow() - timedelta(days=7)
    count = (
        db.query(Message.id)
        .join(Contact, Contact.id == Message.contact_id)
        .filter(
            Contact.company_id == company_id,
            Message.sent_at >= week_start,
            Message.message_type.in_(SEND_TYPES),
        )
        .count()
    )
    return count >= limit


def _has_prior_sent_message(contact_id: int, db: Session) -> bool:
    return (
        db.query(Message.id)
        .filter(Message.contact_id == contact_id)
        .limit(1)
        .first()
        is not None
    )


def _resolve_next_step(state: CampaignState | None) -> tuple[str | None, datetime | None, bool]:
    if state is None:
        return "intro", None, False

    if state.followup_2_sent:
        return None, None, True

    if not state.intro_sent:
        return "intro", None, False

    if not state.followup_1_sent:
        return "followup_1", _safe_sent_at(state.intro_sent_at, state), False

    if not state.followup_2_sent:
        return "followup_2", _safe_sent_at(state.followup_1_sent_at, state), False

    return None, None, True


def _safe_sent_at(sent_at: datetime | None, state: CampaignState) -> datetime:
    if sent_at is not None:
        return sent_at
    if state.updated_at is not None:
        return state.updated_at
    if state.created_at is not None:
        return state.created_at
    return datetime.utcnow()


def _delay_not_reached(last_sent_at: datetime | None, now: datetime, next_step: str | None) -> bool:
    if last_sent_at is None:
        return False

    minimum_wait = timedelta(seconds=settings.min_delay_between_sends_sec)
    if next_step in {"followup_1", "followup_2"}:
        minimum_wait = max(minimum_wait, FOLLOWUP_WAIT)

    return last_sent_at + minimum_wait > now

