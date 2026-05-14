"""Accès Supabase — couche repository pure, zéro logique métier.

Toutes les méthodes absorbent les exceptions réseau et retournent une valeur
nulle plutôt que de propager, afin que l'app fonctionne sans connexion.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
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

    # ── Crédits ───────────────────────────────────────────────────────────────

    def get_user_credits(self, user_id: str) -> int:
        """Retourne les crédits courants de l'utilisateur (0 en cas d'erreur)."""
        try:
            resp = (
                self._client.table("users")
                .select("credits")
                .eq("id", user_id)
                .single()
                .execute()
            )
            return int(resp.data.get("credits", 0))
        except Exception:
            logger.exception("get_user_credits failed for user %s", user_id)
            return 0

    def get_unlocked_count(self, user_id: str) -> int:
        """Nombre de contacts déjà débloqués par cet utilisateur."""
        try:
            resp = (
                self._client.table("contact_unlocks")
                .select("id", count="exact")
                .eq("user_id", user_id)
                .execute()
            )
            return resp.count or 0
        except Exception:
            logger.exception("get_unlocked_count failed for user %s", user_id)
            return 0

    # ── Contacts débloqués ────────────────────────────────────────────────────

    def get_unlocked_contacts(
        self, user_id: str, since: Optional[datetime] = None
    ) -> list[dict]:
        """Contacts débloqués par l'utilisateur, avec delta-sync optionnel.

        Retourne une liste de dicts contenant les champs du contact Supabase.
        """
        try:
            query = (
                self._client.table("contact_unlocks")
                .select("unlocked_at, contacts(*)")
                .eq("user_id", user_id)
            )
            if since is not None:
                query = query.gte("unlocked_at", since.isoformat())
            resp = query.execute()
            return resp.data or []
        except Exception:
            logger.exception("get_unlocked_contacts failed for user %s", user_id)
            return []

    # ── Contribution ──────────────────────────────────────────────────────────

    def upsert_contact(self, email: str, metadata: dict) -> Optional[str]:
        """Insère ou met à jour un contact par email_hash. Retourne l'UUID Supabase."""
        try:
            email_hash = _hash_email(email)
            payload = {
                "email_hash": email_hash,
                **{k: v for k, v in metadata.items() if k != "email"},
            }
            resp = (
                self._client.table("contacts")
                .upsert(payload, on_conflict="email_hash")
                .execute()
            )
            rows = resp.data or []
            if rows:
                return str(rows[0]["id"])
            return None
        except Exception:
            logger.exception("upsert_contact failed for email hash")
            return None

    def create_contribution(self, user_id: str, contact_id: str) -> bool:
        """Enregistre la contribution d'un contact par l'utilisateur.

        Retourne True si l'insertion a réussi, False sinon (y compris doublon).
        """
        try:
            self._client.table("contact_contributions").insert(
                {"user_id": user_id, "contact_id": contact_id}
            ).execute()
            return True
        except Exception:
            logger.exception(
                "create_contribution failed user=%s contact=%s", user_id, contact_id
            )
            return False

    # ── Déblocage ─────────────────────────────────────────────────────────────

    def request_unlock(self, user_id: str, count: int) -> list[dict]:
        """Demande le déblocage de `count` contacts non encore débloqués.

        Sélectionne des contacts visibles non déjà débloqués, insère les
        entrées dans contact_unlocks, et retourne les contacts correspondants.
        """
        try:
            # IDs déjà débloqués par cet utilisateur
            already_resp = (
                self._client.table("contact_unlocks")
                .select("contact_id")
                .eq("user_id", user_id)
                .execute()
            )
            already_ids = {row["contact_id"] for row in (already_resp.data or [])}

            # Contacts visibles pas encore débloqués
            candidates_resp = (
                self._client.table("contacts")
                .select("*")
                .eq("is_visible", True)
                .limit(count + len(already_ids))
                .execute()
            )
            candidates = [
                r for r in (candidates_resp.data or [])
                if r["id"] not in already_ids
            ][:count]

            if not candidates:
                return []

            # Insertion des déblocages
            unlock_rows = [
                {"user_id": user_id, "contact_id": c["id"]} for c in candidates
            ]
            self._client.table("contact_unlocks").insert(unlock_rows).execute()
            return candidates
        except Exception:
            logger.exception("request_unlock failed user=%s count=%d", user_id, count)
            return []

    # ── Événements ────────────────────────────────────────────────────────────

    def record_contact_event(
        self, email: str, event_type: str, user_id: str
    ) -> None:
        """Poste un événement (contacted / replied / bounced) pour un email."""
        try:
            self._client.table("contact_events").insert(
                {
                    "email_hash": _hash_email(email),
                    "event_type": event_type,
                    "user_id": user_id,
                }
            ).execute()
        except Exception:
            logger.exception(
                "record_contact_event failed email_hash=... event=%s", event_type
            )

    def check_already_contacted(self, email_list: list[str]) -> set[str]:
        """Retourne les hashes des emails déjà contactés par n'importe quel utilisateur.

        Utilisé pour la déduplication inter-utilisateurs avant envoi.
        """
        if not email_list:
            return set()
        try:
            hashes = [_hash_email(e) for e in email_list]
            resp = (
                self._client.table("contact_events")
                .select("email_hash")
                .eq("event_type", "contacted")
                .in_("email_hash", hashes)
                .execute()
            )
            return {row["email_hash"] for row in (resp.data or [])}
        except Exception:
            logger.exception("check_already_contacted failed")
            return set()
