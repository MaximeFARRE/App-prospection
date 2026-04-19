from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import unicodedata

from sqlalchemy.orm import Session

from app.models.campaign_state import CampaignState
from app.models.reply import Reply

POSITIVE_KEYWORDS = (
    "interesse",
    "interessee",
    "disponible",
    "oui",
    "volontiers",
    "appel",
)
NEGATIVE_KEYWORDS = (
    "pas interesse",
    "pas interessee",
    "non",
    "stop",
    "desabonner",
    "unsubscribe",
)


@dataclass(slots=True)
class ReplyCandidate:
    contact_id: int
    in_reply_to_message_id: int | None
    subject: str | None
    body: str | None
    from_email: str
    gmail_thread_id: str | None
    received_at: datetime
    campaign_name: str | None = None


@dataclass(slots=True)
class ReplyPersistResult:
    reply_id: int
    created: bool
    sentiment: str
    updated_campaign_states: int


@dataclass(slots=True)
class ReplySentimentUpdateResult:
    reply_id: int
    contact_id: int
    sentiment: str
    updated_campaign_states: int


def classify_sentiment(body: str | None) -> str:
    text = _normalize_for_keyword_match(body)
    if any(keyword in text for keyword in NEGATIVE_KEYWORDS):
        return "negative"
    if any(keyword in text for keyword in POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def record_classified_reply(candidate: ReplyCandidate, db: Session) -> ReplyPersistResult:
    sentiment = classify_sentiment(candidate.body)
    existing = _find_existing_reply(candidate, db)
    created = False

    if existing is None:
        existing = Reply(
            contact_id=candidate.contact_id,
            in_reply_to_message_id=candidate.in_reply_to_message_id,
            subject=candidate.subject,
            body=candidate.body,
            from_email=candidate.from_email,
            gmail_thread_id=candidate.gmail_thread_id,
            sentiment=sentiment,
            received_at=candidate.received_at,
        )
        db.add(existing)
        db.flush()
        created = True
    else:
        existing.sentiment = sentiment

    updated_campaign_states = _mark_contact_replied(
        contact_id=candidate.contact_id,
        campaign_name=candidate.campaign_name,
        sentiment=sentiment,
        db=db,
    )

    return ReplyPersistResult(
        reply_id=existing.id,
        created=created,
        sentiment=sentiment,
        updated_campaign_states=updated_campaign_states,
    )


def update_reply_sentiment(
    reply_id: int,
    sentiment: str,
    db: Session,
) -> ReplySentimentUpdateResult:
    normalized_sentiment = _normalize_sentiment(sentiment)
    if normalized_sentiment is None:
        raise ValueError("Sentiment invalide.")

    reply = db.query(Reply).filter(Reply.id == reply_id).first()
    if reply is None:
        raise ValueError(f"Reply introuvable: {reply_id}")

    reply.sentiment = normalized_sentiment
    updated_campaign_states = _mark_contact_replied(
        contact_id=reply.contact_id,
        campaign_name=None,
        sentiment=normalized_sentiment,
        db=db,
    )
    return ReplySentimentUpdateResult(
        reply_id=reply.id,
        contact_id=reply.contact_id,
        sentiment=normalized_sentiment,
        updated_campaign_states=updated_campaign_states,
    )


def _find_existing_reply(candidate: ReplyCandidate, db: Session) -> Reply | None:
    query = db.query(Reply).filter(
        Reply.contact_id == candidate.contact_id,
        Reply.from_email == candidate.from_email,
        Reply.received_at == candidate.received_at,
    )
    query = _filter_nullable(query, Reply.gmail_thread_id, candidate.gmail_thread_id)
    query = _filter_nullable(query, Reply.subject, candidate.subject)
    query = _filter_nullable(query, Reply.in_reply_to_message_id, candidate.in_reply_to_message_id)
    return query.first()


def _mark_contact_replied(
    contact_id: int,
    campaign_name: str | None,
    sentiment: str,
    db: Session,
) -> int:
    states = _get_campaign_states(contact_id=contact_id, campaign_name=campaign_name, db=db)
    for state in states:
        state.has_replied = True
        state.reply_sentiment = sentiment
    return len(states)


def _get_campaign_states(
    contact_id: int,
    campaign_name: str | None,
    db: Session,
) -> list[CampaignState]:
    if campaign_name is None:
        return db.query(CampaignState).filter(CampaignState.contact_id == contact_id).all()

    state = (
        db.query(CampaignState)
        .filter(
            CampaignState.contact_id == contact_id,
            CampaignState.campaign_name == campaign_name,
        )
        .first()
    )
    if state is not None:
        return [state]

    created_state = CampaignState(contact_id=contact_id, campaign_name=campaign_name)
    db.add(created_state)
    db.flush()
    return [created_state]


def _filter_nullable(query: object, column: object, value: object) -> object:
    if value is None:
        return query.filter(column.is_(None))
    return query.filter(column == value)


def _normalize_for_keyword_match(body: str | None) -> str:
    text = str(body or "").lower()
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_sentiment(value: str) -> str | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"positive", "negative", "neutral", "auto", "unknown"}:
        return normalized
    return None
