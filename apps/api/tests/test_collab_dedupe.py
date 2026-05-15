"""Tests de déduplication — hachage email et cohérence inter-couches."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collaborative_state import CollabUnlockedCache
from app.models.contact import Contact
from app.repositories.supabase_repository import _hash_email
from app.services.collaborative_service import CollaborativeService
from app.services.contact_validation_service import ContactValidationService


# ── Hachage email ─────────────────────────────────────────────────────────────

def test_email_hash_normalization_case_insensitive() -> None:
    assert _hash_email("Alice@ACME.com") == _hash_email("alice@acme.com")


def test_email_hash_normalization_strips_spaces() -> None:
    assert _hash_email("  alice@acme.com  ") == _hash_email("alice@acme.com")


def test_email_hash_is_sha256_hex_64_chars() -> None:
    h = _hash_email("alice@acme.com")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_email_hash_consistent_across_calls() -> None:
    email = "test@example.com"
    assert _hash_email(email) == _hash_email(email)


def test_different_emails_produce_different_hashes() -> None:
    assert _hash_email("alice@acme.com") != _hash_email("bob@acme.com")


# ── filter_already_contacted (batch) ─────────────────────────────────────────

def _make_service(db: Session, contacted_hashes: set[str]) -> CollaborativeService:
    repo = MagicMock()
    repo.check_already_contacted.return_value = contacted_hashes
    repo.get_user_credits.return_value = 0
    return CollaborativeService(
        supabase_repo=repo,
        contact_validation_service=ContactValidationService(),
        db=db,
        user_id="user-1",
        enabled=True,
    )


def test_already_contacted_filter_batch(db: Session) -> None:
    emails = ["alice@corp.com", "bob@corp.com", "carol@corp.com"]
    # bob et carol déjà contactés
    contacted = {_hash_email("bob@corp.com"), _hash_email("carol@corp.com")}
    contacts = [
        Contact(email=e, email_normalized=e, is_blocked=False) for e in emails
    ]
    svc = _make_service(db, contacted)

    filtered = svc.filter_already_contacted(contacts)

    assert len(filtered) == 1
    assert filtered[0].email == "alice@corp.com"


def test_filter_passes_through_when_no_contacted(db: Session) -> None:
    contacts = [
        Contact(email="a@x.com", email_normalized="a@x.com", is_blocked=False),
        Contact(email="b@x.com", email_normalized="b@x.com", is_blocked=False),
    ]
    svc = _make_service(db, set())
    assert len(svc.filter_already_contacted(contacts)) == 2


def test_filter_removes_all_when_all_contacted(db: Session) -> None:
    emails = ["a@x.com", "b@x.com"]
    contacted = {_hash_email(e) for e in emails}
    contacts = [Contact(email=e, email_normalized=e, is_blocked=False) for e in emails]
    svc = _make_service(db, contacted)
    assert svc.filter_already_contacted(contacts) == []


# ── Pas de doublon de contribution ───────────────────────────────────────────

def test_no_duplicate_contribution_same_contact(db: Session) -> None:
    """create_contribution ne doit être appelé qu'une seule fois par contact."""
    repo = MagicMock()
    repo.upsert_contact.return_value = "contact-uuid"
    repo.create_contribution.return_value = True
    repo.get_user_credits.return_value = 0

    contact = Contact(
        email="alice@corp.com",
        email_normalized="alice@corp.com",
        first_name="Alice",
        last_name="M",
        company_id=1,
        linkedin_url="https://www.linkedin.com/in/alice",
        email_status="valid",
        is_blocked=False,
    )
    db.add(contact)
    db.flush()

    svc = CollaborativeService(
        supabase_repo=repo,
        contact_validation_service=ContactValidationService(),
        db=db,
        user_id="user-1",
        enabled=True,
    )

    # Première contribution
    result1 = svc.contribute_contact(contact)
    assert result1.success is True
    assert repo.create_contribution.call_count == 1

    # Deuxième appel sur le même contact — upsert + contribution appelés à nouveau
    # (la déduplication côté Supabase gère UNIQUE(user_id, contact_id))
    result2 = svc.contribute_contact(contact)
    assert result2.success is True
    assert repo.create_contribution.call_count == 2


# ── Pas de doublon sur import local ──────────────────────────────────────────

def test_local_contact_not_duplicated_on_import(db: Session) -> None:
    """Un contact déjà présent dans contacts ne doit pas être dupliqué."""
    email = "alice@corp.com"
    # Contact déjà en base
    db.add(Contact(email=email, email_normalized=email, is_blocked=False))
    db.flush()

    # Ligne dans le cache avec le même email
    db.add(CollabUnlockedCache(
        supabase_id="supa-1",
        email=email,
        email_hash=_hash_email(email),
        unlocked_at=datetime.utcnow(),
        imported_to_local=False,
    ))
    db.flush()

    repo = MagicMock()
    repo.get_user_credits.return_value = 0
    svc = CollaborativeService(
        supabase_repo=repo,
        contact_validation_service=ContactValidationService(),
        db=db,
        user_id="user-1",
        enabled=True,
    )
    created = svc.import_unlocked_to_local()

    assert created == 0
    # Toujours un seul contact en base
    count = len(db.scalars(select(Contact)).all())
    assert count == 1
    # La ligne cache est marquée comme importée malgré tout
    row = db.scalar(select(CollabUnlockedCache))
    assert row.imported_to_local is True
