"""add collaborative fields to contacts and collab_unlocked_cache table

Revision ID: 20260514000000
Revises: 20260419200000
Create Date: 2026-05-14 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260514000000"
down_revision = "20260419200000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Nouvelles colonnes sur contacts ────────────────────────────────────────
    op.add_column(
        "contacts",
        sa.Column("collab_source_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "contacts",
        sa.Column(
            "collab_is_contributed", sa.Boolean(), nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "ix_contacts_collab_source_id", "contacts", ["collab_source_id"]
    )

    # ── Nouvelle table collab_unlocked_cache ───────────────────────────────────
    op.create_table(
        "collab_unlocked_cache",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("supabase_id", sa.String(36), nullable=False),
        sa.Column("email_hash", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("quality_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "imported_to_local", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.Column("unlocked_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supabase_id"),
    )
    op.create_index(
        "ix_collab_unlocked_cache_email_hash", "collab_unlocked_cache", ["email_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_collab_unlocked_cache_email_hash", table_name="collab_unlocked_cache")
    op.drop_table("collab_unlocked_cache")
    op.drop_index("ix_contacts_collab_source_id", table_name="contacts")
    op.drop_column("contacts", "collab_is_contributed")
    op.drop_column("contacts", "collab_source_id")
