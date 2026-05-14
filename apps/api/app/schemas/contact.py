from datetime import datetime

from pydantic import BaseModel

from app.schemas.company import CompanyRead


class ContactBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    sex: str | None = None
    email: str | None = None
    job_title: str | None = None
    country: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    source: str | None = None
    notes: str | None = None


class ContactCreate(ContactBase):
    """Payload pour créer un contact (import CSV ou saisie manuelle)."""
    company_id: int | None = None
    source_prospect_id: str | None = None
    source_business_id: str | None = None


class ContactUpdate(BaseModel):
    """Mise à jour partielle — tous les champs sont optionnels."""
    first_name: str | None = None
    last_name: str | None = None
    sex: str | None = None
    job_title: str | None = None
    country: str | None = None
    city: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    company_id: int | None = None
    notes: str | None = None
    is_blocked: bool | None = None


class ContactRead(ContactBase):
    """Réponse complète renvoyée par l'API."""
    id: int
    email_normalized: str | None
    email_status: str | None
    email_checked_at: datetime | None
    email_check_reason: str | None
    company_id: int | None
    company: CompanyRead | None = None   # eager-loadé si besoin
    source_prospect_id: str | None
    source_business_id: str | None
    is_blocked: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
