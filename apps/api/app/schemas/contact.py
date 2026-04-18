from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ContactBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    company: str | None = None
    job_title: str | None = None
    linkedin_url: str | None = None
    source: str | None = None
    notes: str | None = None


class ContactCreate(ContactBase):
    """Payload pour créer un contact (import CSV ou saisie manuelle)."""
    pass


class ContactUpdate(BaseModel):
    """Payload pour mettre à jour partiellement un contact.
    Tous les champs sont optionnels.
    """
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    job_title: str | None = None
    linkedin_url: str | None = None
    notes: str | None = None
    is_blocked: bool | None = None


class ContactRead(ContactBase):
    """Réponse complète renvoyée par l'API."""
    id: int
    email_normalized: str | None
    is_blocked: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
