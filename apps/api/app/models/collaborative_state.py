from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CollabUnlockedCache(Base):
    """Contacts débloqués depuis Supabase, stockés localement pour usage hors-ligne.

    Cette table est alimentée par CollaborativeService.sync_unlocked_locally()
    et ne doit jamais être modifiée directement par les services existants.
    """

    __tablename__ = "collab_unlocked_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Identifiant Supabase ───────────────────────────────────────────────────
    supabase_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # ── Données contact (email en clair — déchiffré lors du déblocage) ─────────
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    job_title: Mapped[str | None] = mapped_column(String(255))
    company_name: Mapped[str | None] = mapped_column(String(255))
    country: Mapped[str | None] = mapped_column(String(100))
    linkedin_url: Mapped[str | None] = mapped_column(String(500))

    # ── Qualité ────────────────────────────────────────────────────────────────
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    contact_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── Statut local ───────────────────────────────────────────────────────────
    imported_to_local: Mapped[bool] = mapped_column(Boolean, default=False)
    # True une fois que ce contact a été copié dans la table contacts principale

    # ── Timestamps ─────────────────────────────────────────────────────────────
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<CollabUnlockedCache supabase_id={self.supabase_id!r} email_hash={self.email_hash[:8]}...>"
