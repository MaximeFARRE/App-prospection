from __future__ import annotations

from datetime import datetime

from app.models.campaign_state import CampaignState
from app.models.contact import Contact


def norm(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip().lower()


def select_keeper(left: Contact, right: Contact) -> tuple[Contact, Contact]:
    left_score = completeness_score(left)
    right_score = completeness_score(right)

    if left_score > right_score:
        return left, right
    if right_score > left_score:
        return right, left

    if left.created_at and right.created_at and left.created_at != right.created_at:
        return (left, right) if left.created_at < right.created_at else (right, left)

    return (left, right) if left.id < right.id else (right, left)


def completeness_score(contact: Contact) -> int:
    fields = [
        contact.first_name,
        contact.last_name,
        contact.email,
        contact.email_normalized,
        contact.job_title,
        contact.job_level,
        contact.country,
        contact.region,
        contact.city,
        contact.phone,
        contact.linkedin_url,
        contact.email_status,
        contact.company_id,
        contact.source,
        contact.source_prospect_id,
        contact.source_business_id,
        contact.notes,
    ]
    return sum(1 for value in fields if value not in (None, ""))


def merge_contact_fields(keeper: Contact, removed: Contact) -> None:
    for field in [
        "first_name",
        "last_name",
        "job_title",
        "job_level",
        "country",
        "region",
        "city",
        "phone",
        "linkedin_url",
        "email_status",
        "company_id",
        "source",
        "source_prospect_id",
        "source_business_id",
    ]:
        if getattr(keeper, field) in (None, "") and getattr(removed, field) not in (None, ""):
            setattr(keeper, field, getattr(removed, field))

    if keeper.email in (None, "") and removed.email not in (None, ""):
        keeper.email = removed.email
    if keeper.email_normalized in (None, "") and removed.email_normalized not in (None, ""):
        keeper.email_normalized = removed.email_normalized

    keeper.notes = merge_notes(keeper.notes, removed.notes)


def merge_campaign_state(existing: CampaignState, incoming: CampaignState) -> None:
    existing.intro_sent = existing.intro_sent or incoming.intro_sent
    existing.followup_1_sent = existing.followup_1_sent or incoming.followup_1_sent
    existing.followup_2_sent = existing.followup_2_sent or incoming.followup_2_sent
    existing.has_replied = existing.has_replied or incoming.has_replied

    existing.intro_sent_at = min_dt(existing.intro_sent_at, incoming.intro_sent_at)
    existing.followup_1_sent_at = min_dt(existing.followup_1_sent_at, incoming.followup_1_sent_at)
    existing.followup_2_sent_at = min_dt(existing.followup_2_sent_at, incoming.followup_2_sent_at)
    existing.reply_sentiment = merge_sentiment(existing.reply_sentiment, incoming.reply_sentiment)


def merge_notes(keeper_notes: str | None, removed_notes: str | None) -> str | None:
    clean_keeper = (keeper_notes or "").strip()
    clean_removed = (removed_notes or "").strip()

    if clean_keeper and clean_removed:
        if clean_removed in clean_keeper:
            return clean_keeper
        return f"{clean_keeper}\n\n---\n{clean_removed}"
    if clean_keeper:
        return clean_keeper
    if clean_removed:
        return clean_removed
    return None


def merge_sentiment(existing: str | None, incoming: str | None) -> str | None:
    priority = {"positive": 5, "negative": 4, "neutral": 3, "auto": 2, "unknown": 1, None: 0}
    return existing if priority.get(existing, 0) >= priority.get(incoming, 0) else incoming


def min_dt(left: datetime | None, right: datetime | None) -> datetime | None:
    if left is None:
        return right
    if right is None:
        return left
    return left if left <= right else right

