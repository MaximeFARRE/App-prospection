from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.contact import Contact
from app.services import sex_detection_service


class _FakeDetector:
    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = {key.lower(): value for key, value in mapping.items()}

    def get_gender(self, name: str) -> str:
        return self._mapping.get(name.lower(), "unknown")


def test_detect_contacts_sex_updates_only_missing_values(db: Session) -> None:
    missing_1 = _create_contact(db, email="alice@example.com", first_name="Alice", sex=None)
    missing_2 = _create_contact(db, email="bob@example.com", first_name="Bob", sex=None)
    existing = _create_contact(db, email="maxime@example.com", first_name="Maxime", sex="homme")

    detector = _FakeDetector({"alice": "female", "bob": "male"})
    summary = sex_detection_service.detect_contacts_sex_with_detector(
        db,
        detector=detector,
        dry_run=False,
        reset=False,
    )
    db.commit()

    assert summary.total_contacts == 3
    assert summary.updated_contacts == 2
    assert summary.unchanged_contacts == 1
    assert summary.homme_count == 1
    assert summary.femme_count == 1
    assert summary.ambigu_count == 0

    db.refresh(missing_1)
    db.refresh(missing_2)
    db.refresh(existing)
    assert missing_1.sex == "femme"
    assert missing_2.sex == "homme"
    assert existing.sex == "homme"


def test_detect_contacts_sex_reset_recomputes_all_contacts(db: Session) -> None:
    first = _create_contact(db, email="jean@example.com", first_name="Jean", sex="homme")
    second = _create_contact(db, email="unknown@example.com", first_name="", sex="femme")

    detector = _FakeDetector({"jean": "male"})
    summary = sex_detection_service.detect_contacts_sex_with_detector(
        db,
        detector=detector,
        dry_run=False,
        reset=True,
    )
    db.commit()

    assert summary.updated_contacts == 2
    assert summary.unchanged_contacts == 0
    assert summary.homme_count == 1
    assert summary.ambigu_count == 1

    db.refresh(first)
    db.refresh(second)
    assert first.sex == "homme"
    assert second.sex == "ambigu"


def _create_contact(db: Session, email: str, first_name: str | None, sex: str | None) -> Contact:
    contact = Contact(
        first_name=first_name,
        last_name="Test",
        email=email,
        email_normalized=email,
        sex=sex,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact
