from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import GmailAccount
from app.models.company import Company
from app.models.contact import Contact
from app.services import mail_render_service


def test_render_replaces_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = Contact(
        first_name="Alice",
        last_name="Martin",
        sex="femme",
        email="alice@example.com",
        email_normalized="alice@example.com",
        job_title="Analyst",
    )
    setattr(contact, "company", Company(name="Acme"))
    account = GmailAccount(email="sender@example.com")

    subject, body = mail_render_service.render(
        template_subject="Bonjour {{first_name}} ({{sexe}})",
        template_body=(
            "Entreprise {{company}} - Expediteur {{sender_name}} ({{sender_email}}) "
            "- Sexe {{sex}} - Civilite {{civilite}}"
        ),
        contact=contact,
        account=account,
    )

    assert subject == "Bonjour Alice (femme)"
    assert "Entreprise Acme" in body
    assert "Expediteur Maxime (sender@example.com)" in body
    assert "Sexe femme" in body
    assert "Civilite Madame" in body


def test_render_for_contact_loads_template_from_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENDER_NAME", "Maxime")

    contact = Contact(
        first_name="Alice",
        last_name="Martin",
        email="alice@example.com",
        email_normalized="alice@example.com",
    )
    account = GmailAccount(email="sender@example.com")

    subject, body = mail_render_service.render_for_contact("intro", contact, account)

    assert isinstance(subject, str) and subject.strip()
    assert isinstance(body, str) and body.strip()


def test_load_template_raises_when_subject_line_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_read_text(_self: Path, encoding: str = "utf-8") -> str:
        _ = encoding
        return "No subject header"

    monkeypatch.setattr(Path, "read_text", _fake_read_text)

    with pytest.raises(ValueError, match="ligne attendue"):
        mail_render_service.load_template("followup_1")
