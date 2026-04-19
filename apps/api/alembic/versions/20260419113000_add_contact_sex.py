"""Add sex column on contacts

Revision ID: 20260419113000
Revises: 9612052136be
Create Date: 2026-04-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260419113000"
down_revision: Union[str, None] = "9612052136be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("contacts") as batch:
        batch.add_column(sa.Column("sex", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("contacts") as batch:
        batch.drop_column("sex")

