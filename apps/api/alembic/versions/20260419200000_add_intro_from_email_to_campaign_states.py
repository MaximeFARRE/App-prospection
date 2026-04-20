"""add intro_from_email to campaign_states

Revision ID: 20260419200000
Revises: 7083a28cf358
Create Date: 2026-04-19 20:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260419200000"
down_revision = "7083a28cf358"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaign_states",
        sa.Column("intro_from_email", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("campaign_states", "intro_from_email")
