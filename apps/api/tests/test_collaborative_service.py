from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collaborative_state import CollabUnlockedCache
from app.models.contact import Contact
from app.repositories.supabase_repository import _hash_email
from app.services.collaborative_service import CollaborativeService, ContributionResult
from app.services.contact_validation_service import ContactValidationService


# ── Fixtures & helpers ────────────────────────────────────────────────────────

USER_ID = "user-uuid-123"


def _make_repo(**overrides) -> MagicMock:
    """Mock SupabaseRepository avec des valeurs par défaut raisonnables."""
    repo = MagicMock()
    repo.get_user_credits.return_value = 10
    repo.upsert_contact.return_value = "contact-uuid-abc"
    repo.create_contribution.return_value = True
    repo.request_unlock.return_value = []
    repo.check_already_contacted.return_value = set()
    repo.record_contact_event.return_value = None
    for attr, val in overrides.items():
        setattr(repo, attr, val)
    return repo


def _make_service(
    db: Session,
    *,
    enabled: bool = True,
    repo: MagicMock | None = None,
    threshold: int = 60,
) -> CollaborativeService:
    if repo is None:
        repo = _make_repo()
    return CollaborativeService(
        supabase_repo=repo,
        contact_validation_service=ContactValidationService(threshold=threshold),
        db=db,
        user_id=USER_ID,
        enabled=enabled,
    )


def _persisted_contact(db: Session, **kwargs) -> Contact:
    """Crée et persiste un contact en DB."""
    defaults = dict(
        email="alice@acme.com",
        email_normalized="alice@acme.com",
        first_name="Alice",
        last_name="Martin",
        company_id=1,
        linkedin_url="https://www.linkedin.com/in/alice",
        email_status="valid",
        is_blocked=False,
    )
    defaults.update(kwargs)
    contact = Contact(**defaults)
    db.add(contact)
    db.flush()
    return contact


def _cache_row(db: Session, **kwargs) -> CollabUnlockedCache:
    defaults = dict(
        supabase_id="supa-uuid-1",
        email="bob@corp.com",
        email_hash=_hash_email("bob@corp.com"),
        unlocked_at=datetime.utcnow(),
        imported_to_local=False,
    )
    defaults.update(kwargs)
    row = CollabUnlockedCache(**defaults)
    db.add(row)
    db.flush()
    return row


# ── is_enabled ────────────────────────────────────────────────────────────────

def test_disabled_service_returns_false_for_is_enabled(db: Session) -> None:
    svc = _make_service(db, enabled=False)
    assert svc.is_enabled() is False


def test_enabled_service_returns_true_for_is_enabled(db: Session) -> None:
    svc = _make_service(db, enabled=True)
    assert svc.is_enabled() is True


# ── Disabled service — aucun appel réseau ─────────────────────────────────────

def test_disabled_service_skips_all_network_calls(db: Session) -> None:
    repo = _make_repo()
    svc = _make_service(db, enabled=False, repo=repo)

    assert svc.get_credits() == 0
    assert svc.unlock_contacts(5) == []
    assert svc.filter_already_contacted([]) == []
    svc.record_send_event("x@y.com")
    assert svc.import_unlocked_to_local() == 0

    repo.get_user_credits.assert_not_called()
    repo.request_unlock.assert_not_called()
    repo.check_already_contacted.assert_not_called()
    repo.record_contact_event.assert_not_called()


# ── Crédits ───────────────────────────────────────────────────────────────────

def test_credits_returned_as_integer(db: Session) -> None:
    repo = _make_repo()
    repo.get_user_credits.return_value = 7
    svc = _make_service(db, repo=repo)
    assert svc.get_credits() == 7
    repo.get_user_credits.assert_called_once_with(USER_ID)


# ── Contribution ──────────────────────────────────────────────────────────────

def test_contribute_valid_contact_creates_contribution(db: Session) -> None:
    repo = _make_repo()
    contact = _persisted_contact(db)
    svc = _make_service(db, repo=repo)

    result = svc.contribute_contact(contact)

    assert result.success is True
    assert result.contact_id == "contact-uuid-abc"
    assert result.credits_awarded == 0
    repo.upsert_contact.assert_called_once()
    repo.create_contribution.assert_called_once_with(USER_ID, "contact-uuid-abc")
    assert contact.collab_is_contributed is True
    assert contact.collab_source_id == "contact-uuid-abc"


def test_contribute_invalid_contact_returns_rejection(db: Session) -> None:
    repo = _make_repo()
    # Contact sans email → score 0, en dessous du seuil
    contact = _persisted_contact(db, email=None, email_normalized=None, email_status=None)
    svc = _make_service(db, repo=repo)

    result = svc.contribute_contact(contact)

    assert result.success is False
    assert result.rejection_reason is not None
    repo.upsert_contact.assert_not_called()


def test_contribute_disabled_returns_rejection(db: Session) -> None:
    contact = _persisted_contact(db)
    svc = _make_service(db, enabled=False)
    result = svc.contribute_contact(contact)
    assert result.success is False
    assert "désactivé" in (result.rejection_reason or "")


# ── Déblocage ─────────────────────────────────────────────────────────────────

def test_unlock_stores_contacts_in_local_db(db: Session) -> None:
    remote_contacts = [
        {"id": "uuid-1", "email_hash": _hash_email("a@x.com"), "first_name": "Alice"},
        {"id": "uuid-2", "email_hash": _hash_email("b@x.com"), "first_name": "Bob"},
    ]
    repo = _make_repo()
    repo.get_user_credits.return_value = 10
    repo.request_unlock.return_value = remote_contacts
    svc = _make_service(db, repo=repo)

    result = svc.unlock_contacts(2)

    assert len(result) == 2
    rows = db.scalars(select(CollabUnlockedCache)).all()
    assert len(rows) == 2
    ids = {r.supabase_id for r in rows}
    assert ids == {"uuid-1", "uuid-2"}


def test_unlock_blocked_when_credits_insufficient(db: Session) -> None:
    repo = _make_repo()
    repo.get_user_credits.return_value = 1
    svc = _make_service(db, repo=repo)

    result = svc.unlock_contacts(5)

    assert result == []
    repo.request_unlock.assert_not_called()


# ── Déduplication ─────────────────────────────────────────────────────────────

def test_filter_already_contacted_removes_matching_emails(db: Session) -> None:
    contacted_hash = _hash_email("bob@corp.com")
    repo = _make_repo()
    repo.check_already_contacted.return_value = {contacted_hash}

    contacts = [
        Contact(email="alice@acme.com", email_normalized="alice@acme.com", is_blocked=False),
        Contact(email="bob@corp.com",   email_normalized="bob@corp.com",   is_blocked=False),
    ]
    svc = _make_service(db, repo=repo)
    filtered = svc.filter_already_contacted(contacts)

    assert len(filtered) == 1
    assert filtered[0].email == "alice@acme.com"


def test_filter_already_contacted_empty_list_no_call(db: Session) -> None:
    repo = _make_repo()
    svc = _make_service(db, repo=repo)
    result = svc.filter_already_contacted([])
    assert result == []
    repo.check_already_contacted.assert_not_called()


# ── record_send_event ─────────────────────────────────────────────────────────

def test_record_send_event_calls_repo(db: Session) -> None:
    repo = _make_repo()
    svc = _make_service(db, repo=repo)
    svc.record_send_event("alice@acme.com")
    repo.record_contact_event.assert_called_once_with("alice@acme.com", "contacted", USER_ID)


def test_record_send_event_noop_when_disabled(db: Session) -> None:
    repo = _make_repo()
    svc = _make_service(db, enabled=False, repo=repo)
    svc.record_send_event("alice@acme.com")
    repo.record_contact_event.assert_not_called()


# ── import_unlocked_to_local ──────────────────────────────────────────────────

def test_import_unlocked_to_local_creates_contacts(db: Session) -> None:
    _cache_row(db, supabase_id="s1", email="alice@corp.com",
               email_hash=_hash_email("alice@corp.com"))
    _cache_row(db, supabase_id="s2", email="bob@corp.com",
               email_hash=_hash_email("bob@corp.com"))

    svc = _make_service(db)
    created = svc.import_unlocked_to_local()

    assert created == 2
    contacts = db.scalars(select(Contact)).all()
    emails = {c.email for c in contacts}
    assert "alice@corp.com" in emails
    assert "bob@corp.com" in emails


def test_import_unlocked_marks_rows_as_imported(db: Session) -> None:
    row = _cache_row(db)
    svc = _make_service(db)
    svc.import_unlocked_to_local()
    db.refresh(row)
    assert row.imported_to_local is True
