from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
from app.utils.sex_normalization import normalize_sex

CONTACT_PAGE_SIZE_DEFAULT = 50
CONTACT_PAGE_SIZE_MAX = 200
EMAIL_STATUS_MISSING = "__missing__"

def get_all(
    db: Session,
    filters: Mapping[str, Any] | None = None,
) -> list[Contact]:
    """Retourne une liste paginée de contacts avec filtres optionnels."""
    parsed = _parse_filters(filters)
    query = db.query(Contact, Company).outerjoin(Company, Company.id == Contact.company_id)
    query = _apply_filters(query, parsed)

    rows = (
        query
        .order_by(Contact.created_at.desc(), Contact.id.desc())
        .offset(parsed["skip"])
        .limit(parsed["limit"])
        .all()
    )
    return _attach_company(rows)


def get_by_id(db: Session, contact_id: int) -> Contact | None:
    """Retourne un contact avec sa company associée (si présente)."""
    row = (
        db.query(Contact, Company)
        .outerjoin(Company, Company.id == Contact.company_id)
        .filter(Contact.id == contact_id)
        .first()
    )
    if row is None:
        return None

    contact, company = row
    setattr(contact, "company", company)
    return contact


def count(
    db: Session,
    filters: Mapping[str, Any] | None = None,
) -> int:
    """Compte les contacts selon les filtres."""
    parsed = _parse_filters(filters)
    query = db.query(Contact.id).outerjoin(Company, Company.id == Contact.company_id)
    query = _apply_filters(query, parsed)

    return int(query.count())


def search(
    db: Session,
    query: str,
    limit: int = 25,
) -> list[Contact]:
    """Recherche rapide sur nom, email et entreprise."""
    search_query = _clean_text(query)
    if not search_query:
        return []

    needle = f"%{search_query.lower()}%"
    bounded_limit = max(1, min(limit, CONTACT_PAGE_SIZE_MAX))

    rows = (
        db.query(Contact, Company)
        .outerjoin(Company, Company.id == Contact.company_id)
        .filter(
            or_(
                func.lower(func.coalesce(Contact.first_name, "")).like(needle),
                func.lower(func.coalesce(Contact.last_name, "")).like(needle),
                func.lower(func.coalesce(Contact.email, "")).like(needle),
                func.lower(func.coalesce(Contact.email_normalized, "")).like(needle),
                func.lower(func.coalesce(Company.name, "")).like(needle),
            )
        )
        .order_by(Contact.created_at.desc(), Contact.id.desc())
        .limit(bounded_limit)
        .all()
    )
    return _attach_company(rows)


def set_blocked(db: Session, contact_id: int, is_blocked: bool = True) -> Contact | None:
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if contact is None:
        return None
    contact.is_blocked = bool(is_blocked)
    return contact


def set_sex(db: Session, contact_id: int, sex: str | None) -> Contact | None:
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if contact is None:
        return None
    contact.sex = normalize_sex(sex)
    return contact


def get_stats(db: Session) -> dict[str, Any]:
    """Retourne les compteurs globaux du dashboard."""
    contacts_total = int(db.query(func.count(Contact.id)).scalar() or 0)
    companies_total = int(db.query(func.count(Company.id)).scalar() or 0)
    contacts_blocked = int(
        db.query(func.count(Contact.id)).filter(Contact.is_blocked.is_(True)).scalar() or 0
    )
    messages_total = int(db.query(func.count(Message.id)).scalar() or 0)
    messages_intro_sent = int(
        db.query(func.count(Message.id)).filter(Message.message_type == "intro").scalar() or 0
    )
    replies_total = int(db.query(func.count(Reply.id)).scalar() or 0)

    replies_positive = int(
        db.query(func.count(Reply.id)).filter(Reply.sentiment == "positive").scalar() or 0
    )
    replies_negative = int(
        db.query(func.count(Reply.id)).filter(Reply.sentiment == "negative").scalar() or 0
    )
    replies_neutral = int(
        db.query(func.count(Reply.id)).filter(Reply.sentiment == "neutral").scalar() or 0
    )
    replies_auto = int(
        db.query(func.count(Reply.id)).filter(Reply.sentiment == "auto").scalar() or 0
    )
    replies_unknown = int(
        db.query(func.count(Reply.id)).filter(Reply.sentiment == "unknown").scalar() or 0
    )

    reply_rate_percent = round((replies_total / messages_total) * 100, 2) if messages_total else 0.0

    return {
        "contacts_total": contacts_total,
        "companies_total": companies_total,
        "contacts_active": max(contacts_total - contacts_blocked, 0),
        "contacts_blocked": contacts_blocked,
        "messages_total": messages_total,
        "emails_sent_total": messages_total,
        "messages_intro_sent": messages_intro_sent,
        "replies_total": replies_total,
        "reply_rate_percent": reply_rate_percent,
        "replies_positive": replies_positive,
        "replies_negative": replies_negative,
        "replies_neutral": replies_neutral,
        "replies_auto": replies_auto,
        "replies_unknown": replies_unknown,
        "email_status": {
            "valid": _count_email_status(db, "valid"),
            "invalid": _count_email_status(db, "invalid"),
            "unknown": _count_email_status(db, "unknown"),
            "missing": _count_email_status(db, EMAIL_STATUS_MISSING),
        },
    }


def _apply_filters(query, filters: dict[str, Any]):
    if filters["query"]:
        needle = f"%{filters['query'].lower()}%"
        full_name_query = func.trim(
            func.coalesce(Contact.first_name, "") + " " + func.coalesce(Contact.last_name, "")
        )
        query = query.filter(
            or_(
                func.lower(func.coalesce(Contact.first_name, "")).like(needle),
                func.lower(func.coalesce(Contact.last_name, "")).like(needle),
                func.lower(full_name_query).like(needle),
                func.lower(func.coalesce(Contact.email, "")).like(needle),
                func.lower(func.coalesce(Contact.email_normalized, "")).like(needle),
                func.lower(func.coalesce(Company.name, "")).like(needle),
            )
        )

    if filters["name"]:
        needle = f"%{filters['name'].lower()}%"
        full_name = func.trim(
            func.coalesce(Contact.first_name, "") + " " + func.coalesce(Contact.last_name, "")
        )
        query = query.filter(
            or_(
                func.lower(func.coalesce(Contact.first_name, "")).like(needle),
                func.lower(func.coalesce(Contact.last_name, "")).like(needle),
                func.lower(full_name).like(needle),
            )
        )

    if filters["company"]:
        company_needle = f"%{filters['company'].lower()}%"
        query = query.filter(func.lower(func.coalesce(Company.name, "")).like(company_needle))

    if filters["country"]:
        country_needle = f"%{filters['country'].lower()}%"
        query = query.filter(func.lower(func.coalesce(Contact.country, "")).like(country_needle))

    status = _normalize_status(filters["status"])
    if status == "blocked":
        query = query.filter(Contact.is_blocked.is_(True))
    if status == "active":
        query = query.filter(Contact.is_blocked.is_(False))

    email_status = _normalize_email_status(filters["email_status"])
    if email_status == EMAIL_STATUS_MISSING:
        query = query.filter(Contact.email_status.is_(None))
    if email_status and email_status != EMAIL_STATUS_MISSING:
        query = query.filter(func.lower(func.coalesce(Contact.email_status, "")) == email_status)

    return query


def _parse_filters(filters: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(filters or {})
    limit = _to_positive_int(
        payload.get("limit", payload.get("page_size", CONTACT_PAGE_SIZE_DEFAULT)),
        CONTACT_PAGE_SIZE_DEFAULT,
    )
    limit = min(limit, CONTACT_PAGE_SIZE_MAX)

    if "skip" in payload or "offset" in payload:
        skip = _to_positive_int(payload.get("skip", payload.get("offset", 0)), 0)
    else:
        page = _to_positive_int(payload.get("page", 1), 1)
        page = max(page, 1)
        skip = (page - 1) * limit

    return {
        "query": _clean_text(payload.get("query")),
        "name": _clean_text(payload.get("name")),
        "company": _clean_text(payload.get("company")),
        "country": _clean_text(payload.get("country")),
        "status": payload.get("status"),
        "email_status": payload.get("email_status"),
        "skip": skip,
        "limit": limit,
    }


def _attach_company(rows: list[tuple[Contact, Company | None]]) -> list[Contact]:
    contacts: list[Contact] = []
    for contact, company in rows:
        setattr(contact, "company", company)
        contacts.append(contact)
    return contacts


def _normalize_status(value: Any) -> str | None:
    if isinstance(value, bool):
        return "blocked" if value else "active"
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    blocked_values = {"blocked", "block", "bloque", "bloqué", "1", "true", "yes", "inactive"}
    active_values = {"active", "actif", "unblocked", "0", "false", "no"}

    if normalized in blocked_values:
        return "blocked"
    if normalized in active_values:
        return "active"
    return None


def _normalize_email_status(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    if normalized in {"missing", "none", "null", "empty", "vide"}:
        return EMAIL_STATUS_MISSING
    return normalized


def _count_email_status(db: Session, status: str) -> int:
    if status == EMAIL_STATUS_MISSING:
        return int(db.query(func.count(Contact.id)).filter(Contact.email_status.is_(None)).scalar() or 0)

    return int(
        db.query(func.count(Contact.id))
        .filter(func.lower(func.coalesce(Contact.email_status, "")) == status)
        .scalar()
        or 0
    )


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
    if not value:
        return None
    return value
