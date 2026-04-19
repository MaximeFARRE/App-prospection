from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # ── Identité ───────────────────────────────────────────────────────────────
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    sex: Mapped[str | None] = mapped_column(String(10))

    # ── Email (clé de déduplication) ───────────────────────────────────────────
    # Rempli depuis contact_professions_email (ou contact_emails en fallback)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    email_normalized: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)

    # ── Poste ──────────────────────────────────────────────────────────────────
    job_title: Mapped[str | None] = mapped_column(String(255))

    # ── Poste ──────────────────────────────────────────────────────────────────
    job_level: Mapped[str | None] = mapped_column(String(50))
    # valeurs possibles : "c-suite", "senior manager", "manager", "individual"…

    # ── Localisation ───────────────────────────────────────────────────────────
    country: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))

    # ── Contact ────────────────────────────────────────────────────────────────
    phone: Mapped[str | None] = mapped_column(String(50))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))
    email_status: Mapped[str | None] = mapped_column(String(20))
    # valeurs : "valid", "invalid", "unknown" — rempli depuis contact_professional_email_status

    # ── Entreprise ─────────────────────────────────────────────────────────────
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), index=True
    )

    # ── Provenance ─────────────────────────────────────────────────────────────
    source: Mapped[str | None] = mapped_column(String(255))       # nom du fichier CSV
    source_prospect_id: Mapped[str | None] = mapped_column(String(100), index=True)
    source_business_id: Mapped[str | None] = mapped_column(String(100), index=True)

    # ── Notes ──────────────────────────────────────────────────────────────────
    notes: Mapped[str | None] = mapped_column(Text)

    # ── Statut ─────────────────────────────────────────────────────────────────
    is_blocked: Mapped[bool] = mapped_column(default=False)

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Contact id={self.id} email={self.email_normalized!r}>"
