from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_schema_compatibility(engine: Engine) -> None:
    """Ajoute les colonnes manquantes connues pour les bases SQLite historiques."""
    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "contacts" not in table_names:
            return

        contact_columns = {column["name"] for column in inspector.get_columns("contacts")}
        if "sex" not in contact_columns:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN sex VARCHAR(10)"))
        if "email_checked_at" not in contact_columns:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN email_checked_at DATETIME"))
        if "email_check_reason" not in contact_columns:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN email_check_reason VARCHAR(255)"))
        if "notes" not in contact_columns:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN notes TEXT"))
        if "collab_source_id" not in contact_columns:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN collab_source_id VARCHAR(36)"))
        if "collab_is_contributed" not in contact_columns:
            connection.execute(text("ALTER TABLE contacts ADD COLUMN collab_is_contributed BOOLEAN NOT NULL DEFAULT 0"))
