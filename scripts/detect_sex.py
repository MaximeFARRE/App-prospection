"""Détection du sexe des contacts à partir du prénom.

Règle stricte :
  - "homme"  → uniquement si gender-guesser répond "male"
  - "femme"  → uniquement si gender-guesser répond "female"
  - "ambigu" → tout autre cas (mostly_male, mostly_female, andy, unknown,
                prénom vide, initiale seule, prénom composé sans certitude…)

Usage :
    cd apps/api
    .venv\\Scripts\\python ..\\..\\scripts\\detect_sex.py
    .venv\\Scripts\\python ..\\..\\scripts\\detect_sex.py --dry-run   # aperçu sans écriture
    .venv\\Scripts\\python ..\\..\\scripts\\detect_sex.py --reset      # réinitialise tous les sexes d'abord
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Chemin vers apps/api pour importer le code de l'app ───────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

import gender_guesser.detector as _gg_module  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.contact import Contact  # noqa: E402


# ── Constantes ────────────────────────────────────────────────────────────────
HOMME  = "homme"
FEMME  = "femme"
AMBIGU = "ambigu"

# Séparateurs de prénoms composés : "Jean-Pierre", "Anne Marie", "María José"
_COMPOUND_RE = re.compile(r"[\s\-_/]+")


def detect_sex(first_name: str | None, detector: _gg_module.Detector) -> str:
    """Retourne 'homme', 'femme' ou 'ambigu'."""
    if not first_name or not first_name.strip():
        return AMBIGU

    # Normalise : retire les points (initiales "A."), strip des espaces
    cleaned = first_name.strip().rstrip(".")
    if len(cleaned) <= 1:
        return AMBIGU

    # Décompose les prénoms composés et teste chaque partie
    parts = [p.strip() for p in _COMPOUND_RE.split(cleaned) if len(p.strip()) > 1]
    if not parts:
        return AMBIGU

    results = {_classify(part, detector) for part in parts}

    # Si toutes les parties concordent → résultat certain
    if results == {HOMME}:
        return HOMME
    if results == {FEMME}:
        return FEMME

    # Prénom composé mixte ou ambigu → ambigu
    return AMBIGU


def _classify(name: str, detector: _gg_module.Detector) -> str:
    """Applique gender-guesser sur un prénom simple. Seul 'male'/'female' est certain."""
    # gender-guesser est sensible à la casse : première lettre en majuscule
    normalized = name.capitalize()
    result = detector.get_gender(normalized)

    if result == "male":
        return HOMME
    if result == "female":
        return FEMME
    # mostly_male, mostly_female, andy, unknown → ambigu
    return AMBIGU


def run(dry_run: bool, reset: bool) -> None:
    detector = _gg_module.Detector(case_sensitive=False)
    db: Session = SessionLocal()

    try:
        query = db.query(Contact)
        if reset:
            print("  [reset] Remise à NULL de tous les champs sex...")
            if not dry_run:
                db.query(Contact).update({Contact.sex: None})
                db.commit()

        contacts = query.all()
        total = len(contacts)
        print(f"\n  {total} contact(s) à traiter\n")

        counts: dict[str, int] = {HOMME: 0, FEMME: 0, AMBIGU: 0, "inchangé": 0}

        for contact in contacts:
            new_sex = detect_sex(contact.first_name, detector)

            # Si déjà renseigné et non reset → on ne réécrase pas
            if not reset and contact.sex is not None:
                counts["inchangé"] += 1
                continue

            counts[new_sex] += 1

            if not dry_run:
                contact.sex = new_sex

            if dry_run:
                print(
                    f"  [dry-run] id={contact.id:<6} "
                    f"prénom={str(contact.first_name):<20} "
                    f"→ {new_sex}"
                )

        if not dry_run:
            db.commit()
            print("  ✓ Base de données mise à jour.")

        print(f"\n  ── Résultats {'(dry-run) ' if dry_run else ''}──────────────────")
        print(f"  Homme   : {counts[HOMME]}")
        print(f"  Femme   : {counts[FEMME]}")
        print(f"  Ambigu  : {counts[AMBIGU]}")
        print(f"  Inchangé: {counts['inchangé']}")
        print(f"  Total   : {total}\n")

    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Détecte et enregistre le sexe des contacts."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche les résultats sans écrire en base.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Réinitialise le champ sex de tous les contacts avant de recalculer.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(dry_run=args.dry_run, reset=args.reset)
