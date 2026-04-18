"""Initial schema

Revision ID: 20260418204139
Revises:
Create Date: 2026-04-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260418204139"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── companies ──────────────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("source_business_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_companies_name", "companies", ["name"])
    op.create_index("ix_companies_source_business_id", "companies", ["source_business_id"])

    # ── contacts ───────────────────────────────────────────────────────────────
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True, unique=True),
        sa.Column("email_normalized", sa.String(255), nullable=True, unique=True),
        sa.Column("job_title", sa.String(255), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id"), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("source_prospect_id", sa.String(100), nullable=True),
        sa.Column("source_business_id", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_blocked", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_email_normalized", "contacts", ["email_normalized"])
    op.create_index("ix_contacts_company_id", "contacts", ["company_id"])
    op.create_index("ix_contacts_source_prospect_id", "contacts", ["source_prospect_id"])
    op.create_index("ix_contacts_source_business_id", "contacts", ["source_business_id"])

    # ── imports ────────────────────────────────────────────────────────────────
    op.create_table(
        "imports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("total_rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # ── campaign_states ────────────────────────────────────────────────────────
    op.create_table(
        "campaign_states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("campaign_name", sa.String(100), nullable=False),
        sa.Column("intro_sent", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("followup_1_sent", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("followup_2_sent", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("has_replied", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("reply_sentiment", sa.String(20), nullable=True),
        sa.Column("intro_sent_at", sa.DateTime, nullable=True),
        sa.Column("followup_1_sent_at", sa.DateTime, nullable=True),
        sa.Column("followup_2_sent_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_campaign_states_contact_id", "campaign_states", ["contact_id"])
    op.create_index("ix_campaign_states_campaign_name", "campaign_states", ["campaign_name"])

    # ── messages ───────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("campaign_name", sa.String(100), nullable=True),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("from_email", sa.String(255), nullable=False),
        sa.Column("message_type", sa.String(20), nullable=False),
        sa.Column("gmail_message_id", sa.String(255), nullable=True),
        sa.Column("sent_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_messages_contact_id", "messages", ["contact_id"])

    # ── replies ────────────────────────────────────────────────────────────────
    op.create_table(
        "replies",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("contact_id", sa.Integer, sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("in_reply_to_message_id", sa.Integer, sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("from_email", sa.String(255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(255), nullable=True),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("received_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_replies_contact_id", "replies", ["contact_id"])


def downgrade() -> None:
    op.drop_table("replies")
    op.drop_table("messages")
    op.drop_table("campaign_states")
    op.drop_table("imports")
    op.drop_table("contacts")
    op.drop_table("companies")
