from __future__ import annotations

import pytest

from app.models.contact import Contact
from app.services.contact_validation_service import ContactValidationService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _contact(**kwargs) -> Contact:
    """Contact minimal sans enregistrement DB (constructeur SQLAlchemy normal)."""
    return Contact(**kwargs)


def _svc(threshold: int = 60) -> ContactValidationService:
    return ContactValidationService(threshold=threshold)


# ── Tests score ───────────────────────────────────────────────────────────────

def test_valid_professional_contact_scores_high() -> None:
    contact = _contact(
        email="alice@acme.com",
        email_status="valid",
        first_name="Alice",
        last_name="Martin",
        company_id=1,
        linkedin_url="https://www.linkedin.com/in/alice-martin",
    )
    score = _svc().score(contact)
    assert score == 100  # 25+20+15+15+15+10


def test_missing_email_scores_zero() -> None:
    # Aucun champ renseigné → aucun point
    contact = _contact()
    assert _svc().score(contact) == 0


def test_generic_domain_penalized() -> None:
    # gmail.com → pas de points pro-domain
    pro = _contact(email="alice@acme.com", email_status="valid")
    gmail = _contact(email="alice@gmail.com", email_status="valid")
    assert _svc().score(pro) - _svc().score(gmail) == 15


def test_all_consumer_domains_penalized() -> None:
    consumer_emails = [
        "x@hotmail.com", "x@hotmail.fr", "x@yahoo.com", "x@yahoo.fr",
        "x@outlook.com", "x@live.com", "x@free.fr", "x@orange.fr",
        "x@wanadoo.fr", "x@laposte.net", "x@sfr.fr",
    ]
    svc = _svc()
    for email in consumer_emails:
        c = _contact(email=email)
        assert not svc._is_professional_domain(email), f"{email} should be consumer"


def test_invalid_email_format_rejected() -> None:
    contact = _contact(email="not-an-email")
    result = _svc().validate(contact)
    assert result.is_valid is False
    assert "invalide" in (result.rejection_reason or "").lower()


def test_missing_first_name_reduces_score() -> None:
    with_name = _contact(email="a@corp.com", first_name="Alice", last_name="M")
    without_fname = _contact(email="a@corp.com", first_name=None, last_name="M")
    assert _svc().score(with_name) - _svc().score(without_fname) == 15


def test_missing_last_name_reduces_score() -> None:
    with_name = _contact(email="a@corp.com", first_name="Alice", last_name="M")
    without_lname = _contact(email="a@corp.com", first_name="Alice", last_name=None)
    assert _svc().score(with_name) - _svc().score(without_lname) == 15


def test_missing_company_reduces_score() -> None:
    with_co = _contact(email="a@corp.com", company_id=42)
    without_co = _contact(email="a@corp.com", company_id=None)
    assert _svc().score(with_co) - _svc().score(without_co) == 15


def test_linkedin_url_adds_points() -> None:
    with_li = _contact(email="a@corp.com", linkedin_url="https://www.linkedin.com/in/alice")
    without_li = _contact(email="a@corp.com", linkedin_url=None)
    assert _svc().score(with_li) - _svc().score(without_li) == 10


def test_invalid_linkedin_url_not_counted() -> None:
    bad_urls = [
        "https://twitter.com/alice",
        "https://linkedin.com/company/acme",  # company page, not /in/
        "linkedin.com/in/alice",  # missing https
        "",
    ]
    svc = _svc()
    for url in bad_urls:
        c = _contact(email="a@corp.com", linkedin_url=url or None)
        assert not svc._has_valid_linkedin(url if url else None), f"{url!r} should not count"


# ── Tests validate ────────────────────────────────────────────────────────────

def test_score_below_threshold_is_invalid() -> None:
    # email valide (25) + domaine pro (15) = 40, en dessous du seuil 60
    contact = _contact(email="a@corp.com")
    result = _svc(threshold=60).validate(contact)
    assert result.is_valid is False
    assert result.score == 40
    assert "insuffisant" in (result.rejection_reason or "")


def test_score_at_threshold_is_valid() -> None:
    # email valide (25) + pro domain (15) + full name (15) + company (15) = 70 >= 60
    contact = _contact(
        email="a@corp.com",
        first_name="Alice",
        last_name="M",
        company_id=1,
    )
    result = _svc(threshold=60).validate(contact)
    assert result.is_valid is True
    assert result.score == 70


def test_threshold_configurable() -> None:
    contact = _contact(email="a@corp.com")  # score = 25
    assert _svc(threshold=20).validate(contact).is_valid is True
    assert _svc(threshold=60).validate(contact).is_valid is False


def test_missing_email_returns_dedicated_reason() -> None:
    contact = _contact(email=None)
    result = _svc().validate(contact)
    assert result.is_valid is False
    assert "email" in (result.rejection_reason or "").lower()


def test_qev_verified_email_adds_points() -> None:
    verified = _contact(email="a@corp.com", email_status="valid")
    unverified = _contact(email="a@corp.com", email_status="unknown")
    assert _svc().score(verified) - _svc().score(unverified) == 20
