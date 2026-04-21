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
import sys
from pathlib import Path

# ── Chemin vers apps/api pour importer le code de l'app ───────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.services.sex_detection_service import (  # noqa: E402
    AMBIGU,
    FEMME,
    HOMME,
    detect_contacts_sex,
)


def run(dry_run: bool, reset: bool) -> None:
    db: Session = SessionLocal()

    try:
        summary = detect_contacts_sex(db, dry_run=dry_run, reset=reset)

        if not dry_run:
            db.commit()
            print("  ✓ Base de données mise à jour.")

        print(f"\n  ── Résultats {'(dry-run) ' if dry_run else ''}──────────────────")
        print(f"  Homme   : {summary.homme_count}")
        print(f"  Femme   : {summary.femme_count}")
        print(f"  Ambigu  : {summary.ambigu_count}")
        print(f"  Inchangé: {summary.unchanged_contacts}")
        print(f"  Total   : {summary.total_contacts}\n")

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
