from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.contact import Contact


HOMME = "homme"
FEMME = "femme"
AMBIGU = "ambigu"

_COMPOUND_RE = re.compile(r"[\s\-_/]+")


class _GenderDetector(Protocol):
    def get_gender(self, name: str) -> str: ...


@dataclass(slots=True)
class SexDetectionSummary:
    total_contacts: int
    updated_contacts: int
    unchanged_contacts: int
    homme_count: int
    femme_count: int
    ambigu_count: int


def detect_contacts_sex(
    db: Session,
    *,
    dry_run: bool = False,
    reset: bool = False,
) -> SexDetectionSummary:
    """Détecte le sexe des contacts à partir du prénom.

    Règle stricte:
    - homme  si gender-guesser retourne male
    - femme  si gender-guesser retourne female
    - ambigu sinon
    """
    detector = _build_detector()
    return detect_contacts_sex_with_detector(
        db,
        detector=detector,
        dry_run=dry_run,
        reset=reset,
    )


def detect_contacts_sex_with_detector(
    db: Session,
    *,
    detector: _GenderDetector,
    dry_run: bool = False,
    reset: bool = False,
) -> SexDetectionSummary:
    """Version injectable (tests) de detect_contacts_sex."""
    contacts = db.query(Contact).all()
    counts = {HOMME: 0, FEMME: 0, AMBIGU: 0}
    unchanged_contacts = 0
    updated_contacts = 0

    if reset and not dry_run:
        for contact in contacts:
            contact.sex = None

    for contact in contacts:
        if not reset and _has_existing_sex(contact.sex):
            unchanged_contacts += 1
            continue

        detected_sex = detect_sex_from_first_name(contact.first_name, detector)
        counts[detected_sex] += 1

        if not dry_run:
            contact.sex = detected_sex
            updated_contacts += 1

    if not dry_run:
        db.flush()

    return SexDetectionSummary(
        total_contacts=len(contacts),
        updated_contacts=updated_contacts,
        unchanged_contacts=unchanged_contacts,
        homme_count=counts[HOMME],
        femme_count=counts[FEMME],
        ambigu_count=counts[AMBIGU],
    )


def detect_sex_from_first_name(first_name: str | None, detector: _GenderDetector) -> str:
    if not first_name or not first_name.strip():
        return AMBIGU

    cleaned = first_name.strip().rstrip(".")
    if len(cleaned) <= 1:
        return AMBIGU

    parts = [part.strip() for part in _COMPOUND_RE.split(cleaned) if len(part.strip()) > 1]
    if not parts:
        return AMBIGU

    results = {_classify_first_name_part(part, detector) for part in parts}
    if results == {HOMME}:
        return HOMME
    if results == {FEMME}:
        return FEMME
    return AMBIGU


def _classify_first_name_part(name: str, detector: _GenderDetector) -> str:
    result = detector.get_gender(name.capitalize())
    if result == "male":
        return HOMME
    if result == "female":
        return FEMME
    return AMBIGU


def _has_existing_sex(value: str | None) -> bool:
    if value is None:
        return False
    return bool(str(value).strip())


def _build_detector() -> _GenderDetector:
    try:
        import gender_guesser.detector as gg_detector
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Le package 'gender-guesser' est manquant. Installe les dépendances backend."
        ) from exc
    return gg_detector.Detector(case_sensitive=False)
