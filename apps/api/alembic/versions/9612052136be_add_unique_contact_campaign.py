"""add_unique_contact_campaign

Revision ID: 9612052136be
Revises: 20260418220000
Create Date: 2026-04-19 10:24:31.576290

"""
from typing import Sequence, Union

from alembic import op


revision: str = '9612052136be'
down_revision: Union[str, None] = '20260418220000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("campaign_states") as batch_op:
        batch_op.create_unique_constraint(
            "uq_campaign_states_contact_campaign",
            ["contact_id", "campaign_name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("campaign_states") as batch_op:
        batch_op.drop_constraint(
            "uq_campaign_states_contact_campaign",
            type_="unique",
        )
