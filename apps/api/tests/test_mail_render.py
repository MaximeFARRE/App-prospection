from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import GmailAccount
from app.models.company import Company
from app.models.contact import Contact
from app.services import mail_render_service
from app.services.mail_render_service import (
    detect_language,
    list_variants,
    pick_variant_for_position,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_contact(
    contact_id: int = 1,
    country: str | None = None,
    sex: str | None = None,
    first_name: str = "Alice",
    last_name: str = "Martin",
) -> Contact:
    c = Contact(
        first_name=first_name,
        last_name=last_name,
        email=f"contact{contact_id}@example.com",
        email_normalized=f"contact{contact_id}@example.com",
        country=country,
        sex=sex,
    )
    c.id = contact_id
    setattr(c, "company", Company(name="Acme"))
    return c


_ACCOUNT = GmailAccount(email="sender@example.com")


# ── Tests : detect_language ───────────────────────────────────────────────────

def test_france_gets_french_language() -> None:
    assert detect_language(_make_contact(country="france")) == "fr"


def test_france_case_insensitive() -> None:
    assert detect_language(_make_contact(country="France")) == "fr"
    assert detect_language(_make_contact(country="FRANCE")) == "fr"


def test_non_france_gets_english() -> None:
    assert detect_language(_make_contact(country="canada"))      == "en"
    assert detect_language(_make_contact(country="switzerland")) == "en"
    assert detect_language(_make_contact(country="usa"))         == "en"
    assert detect_language(_make_contact(country="uk"))          == "en"


def test_no_country_defaults_to_english() -> None:
    assert detect_language(_make_contact(country=None)) == "en"
    assert detect_language(_make_contact(country=""))   == "en"


# ── Tests : rotation round-robin ─────────────────────────────────────────────

def test_list_variants_returns_sorted_variants() -> None:
    variants = list_variants("intro", "fr")
    assert variants == sorted(variants)
    assert len(variants) >= 2  # au moins a et b existent


def test_list_variants_en() -> None:
    variants = list_variants("intro", "en")
    assert "a" in variants
    assert "b" in variants


def test_pick_variant_rotates_through_all() -> None:
    variants = list_variants("intro", "fr")
    n = len(variants)
    for i, expected in enumerate(variants):
        assert pick_variant_for_position("intro", "fr", i) == expected
    # Retour au début
    assert pick_variant_for_position("intro", "fr", n) == variants[0]


def test_pick_variant_distribution_is_balanced() -> None:
    variants = list_variants("intro", "fr")
    n = len(variants)
    picks = [pick_variant_for_position("intro", "fr", i) for i in range(n * 10)]
    for v in variants:
        assert picks.count(v) == 10


def test_pick_variant_raises_on_invalid_language() -> None:
    with pytest.raises(ValueError):
        pick_variant_for_position("intro", "de", 0)


def test_pick_variant_is_deterministic() -> None:
    assert pick_variant_for_position("intro", "fr", 5) == pick_variant_for_position("intro", "fr", 5)


# ── Tests : règle langue → template ──────────────────────────────────────────

def test_french_contact_gets_fr_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country="france")  # id pair → variant a
    result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
    assert result.language == "fr"
    assert result.ab_variant == "a"
    # Le template FR ne doit pas contenir de mots anglais typiques
    assert "Dear" not in result.subject
    assert "Dear" not in result.body


def test_non_french_contact_gets_en_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country="canada")  # id pair → variant a
    result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
    assert result.language == "en"
    assert result.ab_variant == "a"
    # Le template EN ne doit pas contenir de mots français typiques
    assert "Bonjour" not in result.subject
    assert "Bonjour" not in result.body


def test_no_french_sent_to_english_speaker(monkeypatch: pytest.MonkeyPatch) -> None:
    """On ne doit jamais envoyer de template FR à un contact non-France."""
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    non_france_countries = ["canada", "switzerland", "uk", "usa", "germany", None, ""]
    for country in non_france_countries:
        for contact_id in range(1, 5):
            contact = _make_contact(contact_id=contact_id, country=country)
            result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
            assert result.language == "en", (
                f"Contact pays={country!r} a reçu du FR alors qu'il devrait recevoir de l'EN"
            )


def test_no_english_sent_to_french_contact(monkeypatch: pytest.MonkeyPatch) -> None:
    """On ne doit jamais envoyer de template EN à un contact France."""
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    for contact_id in range(1, 5):
        contact = _make_contact(contact_id=contact_id, country="france")
        result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
        assert result.language == "fr", (
            f"Contact France a reçu de l'EN (id={contact_id})"
        )


# ── Tests : civilité par langue ───────────────────────────────────────────────

def test_french_man_gets_monsieur(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country="france", sex="homme")
    result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
    assert "Monsieur" in result.body or "Monsieur" in result.subject


def test_french_woman_gets_madame(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country="france", sex="femme")
    result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
    assert "Madame" in result.body or "Madame" in result.subject


def test_english_man_gets_mr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country="canada", sex="homme")
    result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
    assert "Mr." in result.body or "Mr." in result.subject


def test_english_woman_gets_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country="canada", sex="femme")
    result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
    assert "Ms." in result.body or "Ms." in result.subject


def test_ambiguous_sex_gets_empty_civility(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    for country in ["france", "canada"]:
        contact = _make_contact(contact_id=2, country=country, sex="ambigu")
        result = mail_render_service.render_for_contact("intro", contact, _ACCOUNT)
        assert "Monsieur" not in result.body
        assert "Madame"   not in result.body
        assert "Mr."      not in result.body
        assert "Ms."      not in result.body


# ── Tests : render() générique ────────────────────────────────────────────────

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
        language="fr",
    )

    assert subject == "Bonjour Alice (femme)"
    assert "Entreprise Acme" in body
    assert "Expediteur Maxime (sender@example.com)" in body
    assert "Sexe femme" in body
    assert "Civilite Madame" in body


# ── Tests : load_template ─────────────────────────────────────────────────────

def test_load_template_raises_on_missing_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_read_text(_self: Path, encoding: str = "utf-8") -> str:
        _ = encoding
        return "No subject header"

    monkeypatch.setattr(Path, "read_text", _fake_read_text)

    with pytest.raises(ValueError, match="ligne attendue"):
        mail_render_service.load_template("followup_1", "fr", "a")


def test_load_template_raises_on_invalid_language() -> None:
    with pytest.raises(ValueError, match="Langue non supportée"):
        mail_render_service.load_template("intro", "de", "a")


def test_load_template_raises_on_invalid_variant() -> None:
    with pytest.raises(ValueError, match="Variant A/B non supporté"):
        mail_render_service.load_template("intro", "fr", "c")


def test_load_template_raises_on_invalid_step() -> None:
    with pytest.raises(ValueError, match="Step de template non supporté"):
        mail_render_service.load_template("intro3", "fr", "a")


# ── Tests : render_for_contact – tous les steps ───────────────────────────────

@pytest.mark.parametrize("step", ["intro", "followup_1", "followup_2"])
@pytest.mark.parametrize("country,expected_lang", [("france", "fr"), ("canada", "en")])
def test_all_steps_render_without_error(
    step: str,
    country: str,
    expected_lang: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mail_render_service, "_load_sender_name", lambda: "Maxime")
    contact = _make_contact(contact_id=2, country=country)
    result = mail_render_service.render_for_contact(step, contact, _ACCOUNT)
    assert isinstance(result.subject, str) and result.subject.strip()
    assert isinstance(result.body, str) and result.body.strip()
    assert result.language == expected_lang
    assert result.ab_variant in {"a", "b"}
