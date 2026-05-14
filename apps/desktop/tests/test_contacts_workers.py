from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.contact import Contact


def _make_in_memory_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, class_=Session)


def _insert_contacts(factory, contacts_data: list[dict]) -> list[int]:
    db = factory()
    ids = []
    try:
        for data in contacts_data:
            c = Contact(**data)
            db.add(c)
        db.flush()
        ids = [c.id for c in db.query(Contact).all()]
        db.commit()
    finally:
        db.close()
    return ids


def _fake_verify(email: str):
    result = MagicMock()
    result.can_send = True
    result.reason = "valid"
    return result


# ── force=False : ne traite que les contacts sans email_status ────────────────

def test_email_verification_worker_no_force():
    from workers.contacts_workers import EmailVerificationWorker

    factory = _make_in_memory_session_factory()
    _insert_contacts(factory, [
        {"email": "alice@example.com", "email_status": None, "is_blocked": False},
        {"email": "bob@example.com",   "email_status": "valid", "is_blocked": False},
    ])

    processed_emails: list[str] = []

    def _fake_verify_tracked(email: str):
        processed_emails.append(email)
        return _fake_verify(email)

    with (
        patch("workers.contacts_workers.SessionLocal", factory),
        patch("workers.contacts_workers.verify_email_for_send", side_effect=_fake_verify_tracked),
    ):
        worker = EmailVerificationWorker(force=False)
        result_payload = {}
        worker.finished.connect(lambda p, e: result_payload.update(p))
        worker.run()

    assert "alice@example.com" in processed_emails
    assert "bob@example.com" not in processed_emails
    assert result_payload["verified"] == 1
    assert result_payload["errors"] == 0


# ── force=True : traite tous les contacts avec un email ───────────────────────

def test_email_verification_worker_force():
    from workers.contacts_workers import EmailVerificationWorker

    factory = _make_in_memory_session_factory()
    _insert_contacts(factory, [
        {"email": "alice@example.com", "email_status": None,    "is_blocked": False},
        {"email": "bob@example.com",   "email_status": "valid", "is_blocked": False},
    ])

    processed_emails: list[str] = []

    def _fake_verify_tracked(email: str):
        processed_emails.append(email)
        return _fake_verify(email)

    with (
        patch("workers.contacts_workers.SessionLocal", factory),
        patch("workers.contacts_workers.verify_email_for_send", side_effect=_fake_verify_tracked),
    ):
        worker = EmailVerificationWorker(force=True)
        result_payload = {}
        worker.finished.connect(lambda p, e: result_payload.update(p))
        worker.run()

    assert "alice@example.com" in processed_emails
    assert "bob@example.com" in processed_emails
    assert result_payload["verified"] == 2
    assert result_payload["errors"] == 0
