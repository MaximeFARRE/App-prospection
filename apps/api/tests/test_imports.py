from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.contact import Contact
from app.models.import_job import ImportJob
from app.services import csv_import_service


def test_import_csv_creates_contact_and_company(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "prospect_first_name": "Alice",
            "prospect_last_name": "Martin",
            "contact_professions_email": "alice@example.com",
            "prospect_company_name": "Acme",
            "prospect_job_title": "Analyst",
            "prospect_country_name": "France",
            "sexe": "F",
            "business_id": "biz-1",
            "prospect_id": "prospect-1",
        }
    ]
    monkeypatch.setattr(csv_import_service, "_read_csv", lambda _path: rows)

    result = csv_import_service.import_csv(Path("prospects.csv"), db, source_name="test-source")

    assert result.total_rows == 1
    assert result.created_contacts == 1
    assert result.created_companies == 1
    assert result.duplicate_count == 0
    assert result.error_count == 0

    contacts = db.query(Contact).all()
    companies = db.query(Company).all()
    jobs = db.query(ImportJob).all()

    assert len(contacts) == 1
    assert contacts[0].email_normalized == "alice@example.com"
    assert contacts[0].sex == "femme"
    assert len(companies) == 1
    assert companies[0].name == "Acme"
    assert len(jobs) == 1
    assert jobs[0].status == "done"


def test_import_csv_skips_duplicate_email(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "prospect_first_name": "Alice",
            "prospect_last_name": "Martin",
            "contact_professions_email": "alice@example.com",
            "prospect_company_name": "Acme",
            "business_id": "biz-1",
            "prospect_id": "prospect-1",
        },
        {
            "prospect_first_name": "Alice",
            "prospect_last_name": "Martin",
            "contact_professions_email": "alice@example.com",
            "prospect_company_name": "Acme",
            "business_id": "biz-1",
            "prospect_id": "prospect-2",
        },
    ]
    monkeypatch.setattr(csv_import_service, "_read_csv", lambda _path: rows)

    result = csv_import_service.import_csv(Path("prospects_duplicates.csv"), db)

    assert result.total_rows == 2
    assert result.created_contacts == 1
    assert result.duplicate_count == 1
    assert result.error_count == 0
    assert db.query(Contact).count() == 1


def test_import_csv_normalizes_gender_alias_column(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "prospect_first_name": "Bob",
            "prospect_last_name": "Durand",
            "contact_professions_email": "bob@example.com",
            "gender": "male",
            "prospect_id": "prospect-42",
        }
    ]
    monkeypatch.setattr(csv_import_service, "_read_csv", lambda _path: rows)

    result = csv_import_service.import_csv(Path("prospects_gender_alias.csv"), db)

    assert result.created_contacts == 1
    saved = db.query(Contact).filter(Contact.email_normalized == "bob@example.com").first()
    assert saved is not None
    assert saved.sex == "homme"
