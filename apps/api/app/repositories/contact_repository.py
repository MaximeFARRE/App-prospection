from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from sqlalchemy import cast, exists, func, or_
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.contact import Contact
from app.models.message import Message
from app.models.reply import Reply
from app.utils.email_normalization import normalize_email
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
    contacts = _attach_company(rows)
    _attach_has_been_contacted(db, contacts)
    return contacts


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


def set_names(
    db: Session,
    contact_id: int,
    first_name: str | None,
    last_name: str | None,
) -> Contact | None:
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if contact is None:
        return None
    contact.first_name = _clean_optional_text(first_name)
    contact.last_name = _clean_optional_text(last_name)
    return contact


def update_contact(db: Session, contact_id: int, fields: dict) -> Contact | None:
    """Met à jour les champs fournis sur un contact existant.

    Gère company_name comme alias vers company_id (lookup ou création).
    Les clés inconnues sont ignorées silencieusement.
    """
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if contact is None:
        return None

    _DIRECT_TEXT = {"first_name", "last_name", "job_title", "country", "city",
                    "phone", "linkedin_url", "notes", "email_check_reason"}
    _DIRECT_OTHER = {"is_blocked", "company_id", "email_status", "email_checked_at"}

    for key, val in fields.items():
        if key == "company_name":
            company = _get_or_create_company_by_name(db, val)
            contact.company_id = company.id if company is not None else None
        elif key == "sex":
            contact.sex = normalize_sex(val)
        elif key in _DIRECT_TEXT:
            setattr(contact, key, _clean_optional_text(val))
        elif key in _DIRECT_OTHER:
            setattr(contact, key, val)

    return contact


def create_manual_contact(
    db: Session,
    *,
    first_name: str | None,
    last_name: str | None,
    email: str,
    company_name: str | None = None,
    job_title: str | None = None,
    sex: str | None = None,
    country: str | None = None,
    city: str | None = None,
    phone: str | None = None,
    linkedin_url: str | None = None,
    notes: str | None = None,
    source: str | None = "manual",
) -> Contact:
    """Crée un contact depuis le formulaire manuel avec validation minimale."""
    email_raw = _clean_optional_text(email)
    email_normalized = normalize_email(email_raw)
    if email_raw is None or email_normalized is None:
        raise ValueError("L'email est obligatoire et doit être valide.")

    existing = (
        db.query(Contact)
        .filter(
            or_(
                Contact.email_normalized == email_normalized,
                func.lower(func.coalesce(Contact.email, "")) == email_normalized,
            )
        )
        .first()
    )
    if existing is not None:
        raise ValueError("Un contact avec cet email existe déjà.")

    company = _get_or_create_company_by_name(db, company_name)
    contact = Contact(
        first_name=_clean_optional_text(first_name),
        last_name=_clean_optional_text(last_name),
        sex=normalize_sex(sex),
        email=email_raw,
        email_normalized=email_normalized,
        company_id=company.id if company is not None else None,
        job_title=_clean_optional_text(job_title),
        country=_clean_optional_text(country),
        city=_clean_optional_text(city),
        phone=_clean_optional_text(phone),
        linkedin_url=_clean_optional_text(linkedin_url),
        source=_clean_optional_text(source) or "manual",
        notes=_clean_optional_text(notes),
    )
    db.add(contact)
    db.flush()
    setattr(contact, "company", company)
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

    today_str = date.today().isoformat()
    today_sends_rows = (
        db.query(Message.from_email, func.count(Message.id))
        .filter(func.strftime("%Y-%m-%d", Message.sent_at) == today_str)
        .group_by(Message.from_email)
        .all()
    )
    today_sends_per_account: dict[str, int] = {
        str(email): int(count) for email, count in today_sends_rows
    }

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
        "today_sends_per_account": today_sends_per_account,
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

    contacted = _normalize_contacted(filters["contacted"])
    if contacted is not None:
        message_exists = exists().where(Message.contact_id == Contact.id)
        if contacted:
            query = query.filter(message_exists)
        else:
            query = query.filter(~message_exists)

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
        "contacted": payload.get("contacted"),
        "skip": skip,
        "limit": limit,
    }


def _attach_company(rows: list[tuple[Contact, Company | None]]) -> list[Contact]:
    contacts: list[Contact] = []
    for contact, company in rows:
        setattr(contact, "company", company)
        contacts.append(contact)
    return contacts


def _attach_has_been_contacted(db: Session, contacts: list[Contact]) -> None:
    for contact in contacts:
        setattr(contact, "has_been_contacted", False)

    contact_ids = [contact.id for contact in contacts]
    if not contact_ids:
        return

    rows = (
        db.query(Message.contact_id)
        .filter(Message.contact_id.in_(contact_ids))
        .distinct()
        .all()
    )
    contacted_ids = {contact_id for (contact_id,) in rows if contact_id is not None}
    for contact in contacts:
        setattr(contact, "has_been_contacted", contact.id in contacted_ids)


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


def _normalize_contacted(value: Any) -> bool | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()
    if not normalized:
        return None

    contacted_values = {"contacted", "yes", "true", "1", "oui"}
    not_contacted_values = {"not_contacted", "no", "false", "0", "non"}
    if normalized in contacted_values:
        return True
    if normalized in not_contacted_values:
        return False
    return None


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


def _clean_optional_text(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    return value if value else None


def _get_or_create_company_by_name(db: Session, company_name: Any) -> Company | None:
    cleaned_name = _clean_optional_text(company_name)
    if cleaned_name is None:
        return None

    existing = (
        db.query(Company)
        .filter(func.lower(func.coalesce(Company.name, "")) == cleaned_name.lower())
        .first()
    )
    if existing is not None:
        return existing

    company = Company(name=cleaned_name)
    db.add(company)
    db.flush()
    return company
