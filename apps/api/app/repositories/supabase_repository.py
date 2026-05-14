"""Accès Supabase — couche repository pure, zéro logique métier.

Toutes les méthodes absorbent les exceptions réseau et retournent une valeur
nulle plutôt que de propager, afin que l'app fonctionne sans connexion.
"""
from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


def _hash_email(email: str) -> str:
    """SHA-256 de l'email normalisé (minuscules, sans espaces).

    Utilisé comme clé de déduplication côté Supabase et pour les
    contact_events — l'email brut ne transite jamais en clair dans les
    colonnes publiques.
    """
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


class SupabaseRepository:
    """Wraps the Supabase Python client with typed, fault-tolerant methods."""

    def __init__(self, client: "Client") -> None:
        self._client = client

    # ── Authentification ──────────────────────────────────────────────────────

    def login(self, email: str, password: str) -> Optional[dict]:
        """Connexion Supabase. Retourne {user_id, user_email} ou None."""
        try:
            resp = self._client.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            return {
                "user_id": str(resp.user.id),
                "user_email": resp.user.email,
            }
        except Exception:
            logger.exception("Supabase login failed for %s", email)
            return None

    def logout(self) -> None:
        """Déconnexion Supabase (best-effort)."""
        try:
            self._client.auth.sign_out()
        except Exception:
            logger.exception("Supabase logout failed")
