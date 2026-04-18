"""Service d'import de fichiers CSV prospects.

Flux pour chaque ligne :
    1. Extraire les données entreprise → get_or_create Company
    2. Extraire les données contact
    3. Normaliser l'email
    4. Vérifier doublon (email_normalized, puis source_prospect_id)
    5. Créer le contact si nouveau
    6. Mettre à jour l'ImportJob avec les stats finales
"""
import csv
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.contact import Contact
from app.models.import_job import ImportJob
from app.utils.csv_mapping import CONTACT_COLUMN_MAP, split_full_name
from app.utils.email_normalization import normalize_email


# ── Résultat retourné au appelant ─────────────────────────────────────────────

@dataclass
class ImportResult:
    job_id: int
    filename: str
    total_rows: int = 0
    created_contacts: int = 0
    created_companies: int = 0
    duplicate_count: int = 0
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


# ── Point d'entrée public ─────────────────────────────────────────────────────

def import_csv(
    file_path: str | Path,
    db: Session,
    source_name: str | None = None,
) -> ImportResult:
    """Importe un fichier CSV de prospects dans la base de données.

    Args:
        file_path:   Chemin vers le fichier CSV.
        db:          Session SQLAlchemy active.
        source_name: Nom affiché dans l'historique (défaut : nom du fichier).

    Returns:
        ImportResult avec le détail des stats.
    """
    file_path = Path(file_path)
    source = source_name or file_path.name

    job = ImportJob(filename=file_path.name, status="processing")
    db.add(job)
    db.flush()

    result = ImportResult(job_id=job.id, filename=file_path.name)

    try:
        rows = _read_csv(file_path)
        result.total_rows = len(rows)

        for i, row in enumerate(rows):
            try:
                _process_row(row, db, source, result)
            except Exception as exc:
                result.error_count += 1
                result.errors.append(f"Ligne {i + 2} : {exc}")

        _update_job(job, result, status="done")
        db.commit()

    except Exception:
        db.rollback()
        job.status = "failed"
        db.commit()
        raise

    return result


# ── Lecture du CSV ────────────────────────────────────────────────────────────

def _read_csv(file_path: Path) -> list[dict[str, str]]:
    """Lit le fichier CSV avec détection automatique de l'encodage et du séparateur."""
    encodings = ("utf-8-sig", "utf-8", "latin-1")
    for encoding in encodings:
        try:
            with open(file_path, encoding=encoding, newline="") as f:
                sample = f.read(4096)
                f.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                except csv.Error:
                    dialect = csv.excel  # fallback : virgule
                reader = csv.DictReader(f, dialect=dialect)
                return [dict(row) for row in reader]
        except UnicodeDecodeError:
            continue

    raise ValueError(f"Impossible de lire le fichier '{file_path.name}' (encodage inconnu).")


# ── Traitement d'une ligne ────────────────────────────────────────────────────

def _process_row(
    row: dict[str, str],
    db: Session,
    source: str,
    result: ImportResult,
) -> None:
    company_id = _get_or_create_company(row, db, result)

    email_raw = _clean(row.get("contact_professions_email"))
    email_norm = normalize_email(email_raw)
    source_prospect_id = _clean(row.get("prospect_id"))

    # Déduplication par email normalisé
    if email_norm and db.query(Contact).filter_by(email_normalized=email_norm).first():
        result.duplicate_count += 1
        return

    # Déduplication par identifiant source (si pas d'email)
    if source_prospect_id and db.query(Contact).filter_by(
        source_prospect_id=source_prospect_id
    ).first():
        result.duplicate_count += 1
        return

    # Noms : colonnes séparées en priorité, fallback sur full_name
    first_name = _clean(row.get("prospect_first_name"))
    last_name = _clean(row.get("prospect_last_name"))
    if not first_name and not last_name:
        first_name, last_name = split_full_name(_clean(row.get("prospect_full_name")))

    contact = Contact(
        first_name=first_name,
        last_name=last_name,
        email=email_raw,
        email_normalized=email_norm,
        job_title=_clean(row.get("prospect_job_title")),
        job_level=_clean(row.get("prospect_job_level_main")),
        country=_clean(row.get("prospect_country_name")),
        region=_clean(row.get("prospect_region_name")),
        city=_clean(row.get("prospect_city")),
        phone=_clean(row.get("contact_mobile_phone")),
        linkedin_url=_clean(row.get("prospect_linkedin")),
        email_status=_clean(row.get("contact_professional_email_status")),
        company_id=company_id,
        source=source,
        source_prospect_id=source_prospect_id,
        source_business_id=_clean(row.get("business_id")),
    )
    db.add(contact)
    result.created_contacts += 1


def _get_or_create_company(
    row: dict[str, str],
    db: Session,
    result: ImportResult,
) -> int | None:
    """Retourne l'id de l'entreprise, la crée si elle n'existe pas encore."""
    name = _clean(row.get("prospect_company_name"))
    if not name:
        return None

    existing = db.query(Company).filter_by(name=name).first()
    if existing:
        return existing.id

    company = Company(
        name=name,
        website=_clean(row.get("prospect_company_website")),
        linkedin_url=_clean(row.get("prospect_company_linkedin")),
        country=_clean(row.get("prospect_country_name")),
        source_business_id=_clean(row.get("business_id")),
    )
    db.add(company)
    db.flush()  # nécessaire pour obtenir company.id avant d'y référencer un contact
    result.created_companies += 1
    return company.id


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(value: str | None) -> str | None:
    """Retourne None si la valeur est vide, blanche ou manquante."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _update_job(job: ImportJob, result: ImportResult, status: str) -> None:
    job.total_rows = result.total_rows
    job.created_count = result.created_contacts
    job.duplicate_count = result.duplicate_count
    job.error_count = result.error_count
    job.status = status
