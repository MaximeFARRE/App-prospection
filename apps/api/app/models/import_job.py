from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportJob(Base):
    """Historique des imports CSV."""

    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(primary_key=True)

    filename: Mapped[str] = mapped_column(String(255))

    # Résultats du traitement
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)   # nouveaux contacts
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)  # ignorés car doublons
    error_count: Mapped[int] = mapped_column(Integer, default=0)      # lignes invalides

    # Statut
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # valeurs possibles : "pending", "processing", "done", "failed"

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ImportJob id={self.id} file={self.filename!r} "
            f"status={self.status!r} created={self.created_count}>"
        )
