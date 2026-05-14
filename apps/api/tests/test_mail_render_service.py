from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import GmailAccount
from app.models.contact import Contact
from app.services import mail_render_service
from app.services.mail_render_service import (
    _markdown_to_html,
    _resolve_civility,
    detect_language,
    list_variants,
    pick_variant_for_position,
    render,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _contact(**kwargs) -> Contact:
    c = Contact()
    for field, value in kwargs.items():
        setattr(c, field, value)
    return c


def _account(email: str = "sender@gmail.com") -> GmailAccount:
    return GmailAccount(
        client_id="cid",
        client_secret="csec",
        refresh_token="rtoken",
        email=email,
    )


def _write_template(directory: Path, step: str, lang: str, variant: str, subject: str, body: str) -> None:
    content = f"Subject: {subject}\n\n{body}\n"
    (directory / f"{step}_{lang}_{variant}.md").write_text(content, encoding="utf-8")


# ── detect_language ───────────────────────────────────────────────────────────

class TestDetectLanguage:
    def test_france_returns_fr(self):
        assert detect_language(_contact(country="France")) == "fr"

    def test_france_case_insensitive(self):
        assert detect_language(_contact(country="FRANCE")) == "fr"

    def test_fr_abbreviation_returns_fr(self):
        assert detect_language(_contact(country="fr")) == "fr"

    def test_fra_returns_fr(self):
        assert detect_language(_contact(country="fra")) == "fr"

    def test_belgium_returns_en(self):
        assert detect_language(_contact(country="Belgium")) == "en"

    def test_none_country_returns_en(self):
        assert detect_language(_contact(country=None)) == "en"

    def test_empty_country_returns_en(self):
        assert detect_language(_contact(country="")) == "en"


# ── _resolve_civility ─────────────────────────────────────────────────────────

class TestResolveCivility:
    def test_homme_french(self):
        assert _resolve_civility("homme", "fr") == "Monsieur"

    def test_femme_french(self):
        assert _resolve_civility("femme", "fr") == "Madame"

    def test_homme_english(self):
        assert _resolve_civility("homme", "en") == "Mr."

    def test_femme_english(self):
        assert _resolve_civility("femme", "en") == "Ms."

    def test_unknown_sex_returns_empty(self):
        assert _resolve_civility("unknown", "fr") == ""
        assert _resolve_civility("", "en") == ""


# ── _markdown_to_html ─────────────────────────────────────────────────────────

class TestMarkdownToHtml:
    def test_empty_returns_empty(self):
        assert _markdown_to_html("") == ""

    def test_single_paragraph_wrapped_in_p(self):
        result = _markdown_to_html("Hello world")
        assert result == "<p>Hello world</p>"

    def test_two_paragraphs_separated_by_blank_line(self):
        result = _markdown_to_html("Para 1\n\nPara 2")
        assert "<p>Para 1</p>" in result
        assert "<p>Para 2</p>" in result

    def test_single_newline_becomes_br(self):
        result = _markdown_to_html("Line 1\nLine 2")
        assert "<br>" in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_multiple_blank_lines_treated_as_one_separator(self):
        result = _markdown_to_html("Para 1\n\n\nPara 2")
        assert result.count("<p>") == 2

    def test_crlf_normalised(self):
        result = _markdown_to_html("Para 1\r\n\r\nPara 2")
        assert result.count("<p>") == 2


# ── list_variants / pick_variant_for_position ─────────────────────────────────

class TestListAndPickVariants:
    def test_lists_existing_variants(self, tmp_path: Path):
        _write_template(tmp_path, "intro", "fr", "a", "Subject", "Body A")
        _write_template(tmp_path, "intro", "fr", "b", "Subject", "Body B")

        with patch.object(mail_render_service, "_TEMPLATES_DIR", tmp_path):
            variants = list_variants("intro", "fr")

        assert variants == ["a", "b"]

    def test_empty_when_no_templates(self, tmp_path: Path):
        with patch.object(mail_render_service, "_TEMPLATES_DIR", tmp_path):
            variants = list_variants("intro", "fr")

        assert variants == []

    def test_pick_variant_round_robin(self, tmp_path: Path):
        _write_template(tmp_path, "intro", "fr", "a", "Subject", "Body A")
        _write_template(tmp_path, "intro", "fr", "b", "Subject", "Body B")

        with patch.object(mail_render_service, "_TEMPLATES_DIR", tmp_path):
            assert pick_variant_for_position("intro", "fr", 0) == "a"
            assert pick_variant_for_position("intro", "fr", 1) == "b"
            assert pick_variant_for_position("intro", "fr", 2) == "a"  # wraps around

    def test_pick_variant_raises_when_no_templates(self, tmp_path: Path):
        with patch.object(mail_render_service, "_TEMPLATES_DIR", tmp_path):
            with pytest.raises(ValueError, match="Aucun template"):
                pick_variant_for_position("intro", "fr", 0)

    def test_invalid_step_raises(self, tmp_path: Path):
        with patch.object(mail_render_service, "_TEMPLATES_DIR", tmp_path):
            with pytest.raises(ValueError):
                list_variants("unknown_step", "fr")

    def test_invalid_language_raises(self, tmp_path: Path):
        with patch.object(mail_render_service, "_TEMPLATES_DIR", tmp_path):
            with pytest.raises(ValueError):
                list_variants("intro", "de")


# ── render ────────────────────────────────────────────────────────────────────

class TestRender:
    def test_substitutes_first_and_last_name(self):
        contact = _contact(first_name="Jean", last_name="Dupont", sex="homme", country="Belgium")
        account = _account()

        with patch.object(mail_render_service, "_load_sender_name", return_value="Alice"):
            subject, body = render("Hello {{first_name}}", "Dear {{civilite}} {{last_name}}", contact, account, language="en")

        assert subject == "Hello Jean"
        assert "Mr." in body
        assert "Dupont" in body

    def test_substitutes_sender_email(self):
        contact = _contact(first_name="Jean", last_name="Dupont", sex=None, country=None)
        account = _account("expediteur@gmail.com")

        with patch.object(mail_render_service, "_load_sender_name", return_value="Alice"):
            _, body = render("Subj", "From {{sender_email}}", contact, account, language="fr")

        assert "expediteur@gmail.com" in body

    def test_substitutes_sender_name(self):
        contact = _contact(first_name="Jean", last_name="Dupont", sex=None, country=None)
        account = _account()

        with patch.object(mail_render_service, "_load_sender_name", return_value="Maxime"):
            _, body = render("Subj", "Signed {{sender_name}}", contact, account, language="fr")

        assert "Maxime" in body

    def test_unknown_variable_left_intact(self):
        contact = _contact(first_name="Jean", last_name="Dupont", sex=None, country=None)
        account = _account()

        with patch.object(mail_render_service, "_load_sender_name", return_value=""):
            _, body = render("Subj", "{{unknown_var}}", contact, account, language="fr")

        assert "{{unknown_var}}" in body

    def test_french_civility_for_femme(self):
        contact = _contact(first_name="Marie", last_name="Curie", sex="femme", country="France")
        account = _account()

        with patch.object(mail_render_service, "_load_sender_name", return_value=""):
            _, body = render("Subj", "Bonjour {{civilite}}", contact, account, language="fr")

        assert "Madame" in body

    def test_full_name_variable(self):
        contact = _contact(first_name="Jean", last_name="Dupont", sex=None, country=None)
        account = _account()

        with patch.object(mail_render_service, "_load_sender_name", return_value=""):
            _, body = render("Subj", "{{full_name}}", contact, account, language="fr")

        assert body == "Jean Dupont"
