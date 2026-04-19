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

