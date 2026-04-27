from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from app.db.schema_compat import ensure_schema_compatibility


def test_ensure_schema_compatibility_adds_contacts_sex_column() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100)
                )
                """
            )
        )

    ensure_schema_compatibility(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("contacts")}
    assert "sex" in columns


def test_ensure_schema_compatibility_adds_email_verification_columns() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    sex VARCHAR(10),
                    email_status VARCHAR(20)
                )
                """
            )
        )

    ensure_schema_compatibility(engine)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("contacts")}
    assert "email_checked_at" in columns
    assert "email_check_reason" in columns
