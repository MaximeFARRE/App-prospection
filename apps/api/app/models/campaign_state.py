from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampaignState(Base):
    """État d'un contact dans une campagne donnée.

    Une ligne = un contact dans une campagne.
    La combinaison (contact_id, campaign_name) est unique.
    """

    __tablename__ = "campaign_states"
    __table_args__ = (
        UniqueConstraint("contact_id", "campaign_name", name="uq_campaign_states_contact_campaign"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    campaign_name: Mapped[str] = mapped_column(String(100), index=True)

    # Progression des envois
    intro_sent: Mapped[bool] = mapped_column(default=False)
    followup_1_sent: Mapped[bool] = mapped_column(default=False)
    followup_2_sent: Mapped[bool] = mapped_column(default=False)

    # Réponse
    has_replied: Mapped[bool] = mapped_column(default=False)
    reply_sentiment: Mapped[str | None] = mapped_column(String(20))
    # valeurs possibles : "positive", "negative", "neutral", "auto", "unknown"

    # Timestamps des envois
    intro_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    followup_1_sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    followup_2_sent_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignState contact_id={self.contact_id} "
            f"campaign={self.campaign_name!r} intro={self.intro_sent}>"
        )
