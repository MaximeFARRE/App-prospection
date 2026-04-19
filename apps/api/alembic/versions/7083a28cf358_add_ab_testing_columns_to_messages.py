"""add_ab_testing_columns_to_messages

Revision ID: 7083a28cf358
Revises: 20260419113000
Create Date: 2026-04-19 11:27:09.624209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7083a28cf358'
down_revision: Union[str, None] = '20260419113000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.add_column(sa.Column("language",   sa.String(5), nullable=True))
        batch.add_column(sa.Column("ab_variant", sa.String(5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("ab_variant")
        batch.drop_column("language")
