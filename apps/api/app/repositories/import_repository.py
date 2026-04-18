from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.models.import_job import ImportJob


IMPORT_PAGE_SIZE_DEFAULT = 100
IMPORT_PAGE_SIZE_MAX = 500


def get_all(
    db: Session,
    filters: Mapping[str, Any] | None = None,
) -> list[ImportJob]:
    """Retourne l'historique des imports (du plus récent au plus ancien)."""
    parsed = _parse_filters(filters)
    return (
        db.query(ImportJob)
        .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        .offset(parsed["skip"])
        .limit(parsed["limit"])
        .all()
    )


def _parse_filters(filters: Mapping[str, Any] | None) -> dict[str, int]:
    payload = dict(filters or {})

    limit = _to_positive_int(payload.get("limit", IMPORT_PAGE_SIZE_DEFAULT), IMPORT_PAGE_SIZE_DEFAULT)
    limit = min(limit, IMPORT_PAGE_SIZE_MAX)
    skip = _to_positive_int(payload.get("skip", 0), 0)

    return {"skip": skip, "limit": limit}


def _to_positive_int(raw_value: Any, default: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(value, 0)

