"""add quality_score to contacts

Revision ID: 20260515000000
Revises: 20260514000000
Create Date: 2026-05-15 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260515000000"
down_revision = "20260514000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("quality_score", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contacts", "quality_score")
