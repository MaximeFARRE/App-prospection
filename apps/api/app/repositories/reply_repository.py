from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.models.reply import Reply

REPLY_PAGE_SIZE_DEFAULT = 100
REPLY_PAGE_SIZE_MAX = 200


def get_all(db: Session, filters: Mapping[str, Any] | None = None) -> list[Reply]:
    parsed = _parse_filters(filters)
    query = db.query(Reply, Contact).outerjoin(Contact, Contact.id == Reply.contact_id)
    query = _apply_filters(query, parsed)

    rows = (
        query
        .order_by(Reply.received_at.desc(), Reply.id.desc())
        .offset(parsed["skip"])
        .limit(parsed["limit"])
        .all()
    )
    return _attach_contact(rows)


def count(db: Session, filters: Mapping[str, Any] | None = None) -> int:
    parsed = _parse_filters(filters)
    query = db.query(Reply.id).outerjoin(Contact, Contact.id == Reply.contact_id)
    query = _apply_filters(query, parsed)
    return int(query.count())


def _apply_filters(query, filters: dict[str, Any]):
    if filters["query"]:
        needle = f"%{filters['query'].lower()}%"
        full_name = func.trim(func.coalesce(Contact.first_name, "") + " " + func.coalesce(Contact.last_name, ""))
        query = query.filter(
            or_(
                func.lower(func.coalesce(Contact.first_name, "")).like(needle),
                func.lower(func.coalesce(Contact.last_name, "")).like(needle),
                func.lower(full_name).like(needle),
                func.lower(func.coalesce(Reply.from_email, "")).like(needle),
                func.lower(func.coalesce(Reply.subject, "")).like(needle),
            )
        )

    if filters["sentiment"]:
        query = query.filter(func.lower(func.coalesce(Reply.sentiment, "")) == filters["sentiment"])

    return query


def _parse_filters(filters: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(filters or {})
    limit = _to_positive_int(
        payload.get("limit", payload.get("page_size", REPLY_PAGE_SIZE_DEFAULT)),
        REPLY_PAGE_SIZE_DEFAULT,
    )
    limit = min(limit, REPLY_PAGE_SIZE_MAX)

    if "skip" in payload or "offset" in payload:
        skip = _to_positive_int(payload.get("skip", payload.get("offset", 0)), 0)
    else:
        page = _to_positive_int(payload.get("page", 1), 1)
        page = max(page, 1)
        skip = (page - 1) * limit

    return {
        "query": _clean_text(payload.get("query")),
        "sentiment": _normalize_sentiment(payload.get("sentiment")),
        "skip": skip,
        "limit": limit,
    }


def _attach_contact(rows: list[tuple[Reply, Contact | None]]) -> list[Reply]:
    replies: list[Reply] = []
    for reply, contact in rows:
        setattr(reply, "contact", contact)
        replies.append(reply)
    return replies


def _normalize_sentiment(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    return normalized if normalized else None


def _to_positive_int(raw_value: Any, default: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(value, 0)


def _clean_text(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value if value else None
