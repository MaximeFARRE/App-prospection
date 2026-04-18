from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Reply(Base):
    """Historique des réponses reçues."""

    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True)

    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id"), index=True)

    # Lien vers le mail auquel on répond (optionnel)
    in_reply_to_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id")
    )

    # Contenu
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str | None] = mapped_column(Text)

    # Origine
    from_email: Mapped[str] = mapped_column(String(255))
    gmail_thread_id: Mapped[str | None] = mapped_column(String(255))

    # Classification
    sentiment: Mapped[str | None] = mapped_column(String(20))
    # valeurs possibles : "positive", "negative", "neutral", "auto", "unknown"

    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<Reply id={self.id} contact_id={self.contact_id} "
            f"sentiment={self.sentiment!r}>"
        )
