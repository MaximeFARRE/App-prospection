"""Add contact location, job_level and email_status

Revision ID: 20260418220000
Revises: 20260418204139
Create Date: 2026-04-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260418220000"
down_revision: Union[str, None] = "20260418204139"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("contacts") as batch:
        batch.add_column(sa.Column("job_level",    sa.String(50),  nullable=True))
        batch.add_column(sa.Column("region",       sa.String(100), nullable=True))
        batch.add_column(sa.Column("city",         sa.String(100), nullable=True))
        batch.add_column(sa.Column("email_status", sa.String(20),  nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("contacts") as batch:
        batch.drop_column("email_status")
        batch.drop_column("city")
        batch.drop_column("region")
        batch.drop_column("job_level")
