"""add contact_count to collab_unlocked_cache

Revision ID: 20260515100000
Revises: 20260515000000
Create Date: 2026-05-15 10:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260515100000"
down_revision = "20260515000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collab_unlocked_cache",
        sa.Column("contact_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("collab_unlocked_cache", "contact_count")
