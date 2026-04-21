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
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.contact import Contact
from app.models.import_job import ImportJob
from app.utils.csv_mapping import split_full_name
from app.utils.email_normalization import normalize_email
from app.utils.sex_normalization import normalize_sex


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


# ── Alias de colonnes (anciens + nouveaux formats CSV) ───────────────────────

FIRST_NAME_COLUMNS: tuple[str, ...] = ("prospect_first_name", "First Name")
LAST_NAME_COLUMNS: tuple[str, ...] = ("prospect_last_name", "Last Name")
FULL_NAME_COLUMNS: tuple[str, ...] = ("prospect_full_name", "Full Name")

EMAIL_COLUMNS: tuple[str, ...] = (
    "contact_professions_email",
    "Work Email",
    "Personal Email",
    "Additional Email 1",
    "Additional Email 2",
    "Additional Email 3",
    "contact_emails",
)

SOURCE_PROSPECT_ID_COLUMNS: tuple[str, ...] = ("prospect_id", "Prospect ID")
SOURCE_BUSINESS_ID_COLUMNS: tuple[str, ...] = ("business_id", "Business ID")

JOB_TITLE_COLUMNS: tuple[str, ...] = ("prospect_job_title", "Title", "Headline")
JOB_LEVEL_COLUMNS: tuple[str, ...] = ("prospect_job_level_main",)
LINKEDIN_COLUMNS: tuple[str, ...] = ("prospect_linkedin", "Linkedin URL", "LinkedIn URL")

COUNTRY_COLUMNS: tuple[str, ...] = ("prospect_country_name", "Country")
REGION_COLUMNS: tuple[str, ...] = ("prospect_region_name", "Region")
CITY_COLUMNS: tuple[str, ...] = ("prospect_city", "City")
LOCATION_COLUMNS: tuple[str, ...] = ("Location",)

PHONE_COLUMNS: tuple[str, ...] = (
    "contact_mobile_phone",
    "Phone",
    "Phone 2",
    "Phone 3",
    "Phone 4",
)
EMAIL_STATUS_COLUMNS: tuple[str, ...] = (
    "contact_professional_email_status",
    "Work Email Status",
)
SEX_COLUMNS: tuple[str, ...] = (
    "sexe",
    "sex",
    "gender",
    "Gender",
    "prospect_gender",
    "contact_gender",
)

COMPANY_NAME_COLUMNS: tuple[str, ...] = ("prospect_company_name", "Company")
COMPANY_WEBSITE_COLUMNS: tuple[str, ...] = ("prospect_company_website", "Company Website")
COMPANY_LINKEDIN_COLUMNS: tuple[str, ...] = (
    "prospect_company_linkedin",
    "Company Linkedin URL",
    "Company LinkedIn URL",
)

_EMAIL_SPLITTER = re.compile(r"[;,|]")


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
    seen_emails: set[str] = set()
    seen_source_prospect_ids: set[str] = set()

    try:
        rows = _read_csv(file_path)
        result.total_rows = len(rows)

        for i, row in enumerate(rows):
            try:
                _process_row(
                    row=row,
                    db=db,
                    source=source,
                    result=result,
                    seen_emails=seen_emails,
                    seen_source_prospect_ids=seen_source_prospect_ids,
                )
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
    seen_emails: set[str],
    seen_source_prospect_ids: set[str],
) -> None:
    row_lookup = _build_row_lookup(row)

    email_raw, email_norm = _extract_primary_email(row, row_lookup)
    if email_norm is None:
        raise ValueError("Email manquant ou invalide (contact non importé).")

    company_id = _get_or_create_company(row, row_lookup, db, result)
    source_prospect_id = _row_get(row, row_lookup, SOURCE_PROSPECT_ID_COLUMNS)
    country, region, city = _extract_location(row, row_lookup)

    if email_norm and email_norm in seen_emails:
        result.duplicate_count += 1
        return

    if source_prospect_id and source_prospect_id in seen_source_prospect_ids:
        result.duplicate_count += 1
        return

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
    first_name = _row_get(row, row_lookup, FIRST_NAME_COLUMNS)
    last_name = _row_get(row, row_lookup, LAST_NAME_COLUMNS)
    if not first_name and not last_name:
        first_name, last_name = split_full_name(_row_get(row, row_lookup, FULL_NAME_COLUMNS))

    contact = Contact(
        first_name=first_name,
        last_name=last_name,
        sex=_extract_sex(row, row_lookup),
        email=email_raw,
        email_normalized=email_norm,
        job_title=_row_get(row, row_lookup, JOB_TITLE_COLUMNS),
        job_level=_row_get(row, row_lookup, JOB_LEVEL_COLUMNS),
        country=country,
        region=region,
        city=city,
        phone=_row_get(row, row_lookup, PHONE_COLUMNS),
        linkedin_url=_row_get(row, row_lookup, LINKEDIN_COLUMNS),
        email_status=_row_get(row, row_lookup, EMAIL_STATUS_COLUMNS),
        company_id=company_id,
        source=source,
        source_prospect_id=source_prospect_id,
        source_business_id=_row_get(row, row_lookup, SOURCE_BUSINESS_ID_COLUMNS),
    )
    db.add(contact)
    if email_norm:
        seen_emails.add(email_norm)
    if source_prospect_id:
        seen_source_prospect_ids.add(source_prospect_id)
    result.created_contacts += 1


def _get_or_create_company(
    row: dict[str, str],
    row_lookup: dict[str, str],
    db: Session,
    result: ImportResult,
) -> int | None:
    """Retourne l'id de l'entreprise, la crée si elle n'existe pas encore."""
    name = _row_get(row, row_lookup, COMPANY_NAME_COLUMNS)
    if not name:
        return None

    existing = db.query(Company).filter_by(name=name).first()
    if existing:
        return existing.id

    country, _, _ = _extract_location(row, row_lookup)
    company = Company(
        name=name,
        website=_row_get(row, row_lookup, COMPANY_WEBSITE_COLUMNS),
        linkedin_url=_row_get(row, row_lookup, COMPANY_LINKEDIN_COLUMNS),
        country=country,
        source_business_id=_row_get(row, row_lookup, SOURCE_BUSINESS_ID_COLUMNS),
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


def _normalize_header(header: str) -> str:
    """Normalise un nom de colonne pour une comparaison robuste."""
    return " ".join(header.strip().lower().split())


def _build_row_lookup(row: dict[str, str]) -> dict[str, str]:
    """Construit un index case-insensitive des colonnes de la ligne."""
    lookup: dict[str, str] = {}
    for key, value in row.items():
        if not isinstance(key, str):
            continue
        lookup[_normalize_header(key)] = value
    return lookup


def _row_get(
    row: dict[str, str],
    row_lookup: dict[str, str],
    columns: tuple[str, ...],
) -> str | None:
    """Retourne la première valeur non vide trouvée parmi des alias de colonnes."""
    for column in columns:
        value = _clean(row.get(column))
        if value:
            return value

    for column in columns:
        value = _clean(row_lookup.get(_normalize_header(column)))
        if value:
            return value

    return None


def _extract_primary_email(
    row: dict[str, str],
    row_lookup: dict[str, str],
) -> tuple[str | None, str | None]:
    """Choisit le premier email valide parmi les colonnes supportées."""
    for column in EMAIL_COLUMNS:
        raw_value = _row_get(row, row_lookup, (column,))
        if not raw_value:
            continue
        candidates = [raw_value]
        if _EMAIL_SPLITTER.search(raw_value):
            candidates = [part.strip() for part in _EMAIL_SPLITTER.split(raw_value) if part.strip()]

        for candidate in candidates:
            normalized = normalize_email(candidate)
            if normalized:
                return candidate, normalized

    return None, None


def _extract_location(
    row: dict[str, str],
    row_lookup: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Extrait country/region/city, avec fallback depuis une colonne Location."""
    country = _row_get(row, row_lookup, COUNTRY_COLUMNS)
    region = _row_get(row, row_lookup, REGION_COLUMNS)
    city = _row_get(row, row_lookup, CITY_COLUMNS)

    if country or region or city:
        return country, region, city

    location = _row_get(row, row_lookup, LOCATION_COLUMNS)
    if not location:
        return None, None, None

    parts = [part.strip() for part in location.split(",") if part.strip()]
    if len(parts) == 1:
        return None, parts[0], None
    if len(parts) == 2:
        return parts[1], None, parts[0]

    return parts[-1], ", ".join(parts[1:-1]), parts[0]


def _extract_sex(
    row: dict[str, str],
    row_lookup: dict[str, str],
) -> str | None:
    for column in SEX_COLUMNS:
        normalized = normalize_sex(_row_get(row, row_lookup, (column,)))
        if normalized is not None:
            return normalized
    return None


def _update_job(job: ImportJob, result: ImportResult, status: str) -> None:
    job.total_rows = result.total_rows
    job.created_count = result.created_contacts
    job.duplicate_count = result.duplicate_count
    job.error_count = result.error_count
    job.status = status
