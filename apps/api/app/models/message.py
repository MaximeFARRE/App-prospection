from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Message(Base):
    """Historique de tous les mails envoyés."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)

    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)
    campaign_name: Mapped[str | None] = mapped_column(String(100))

    # Contenu
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)

    # Expéditeur
    from_email: Mapped[str] = mapped_column(String(255))

    # Type d'envoi
    message_type: Mapped[str] = mapped_column(String(20))
    # valeurs possibles : "intro", "followup_1", "followup_2"

    # Résultat
    gmail_message_id: Mapped[str | None] = mapped_column(String(255))
    # bounced et error_message pour la gestion des erreurs futures

    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<Message id={self.id} contact_id={self.contact_id} "
            f"type={self.message_type!r}>"
        )
