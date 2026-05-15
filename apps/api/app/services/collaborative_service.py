"""Logique métier collaborative — crédits, contributions, déblocages, déduplication.

Ce service ne fait aucun appel réseau directement : tout passe par
SupabaseRepository. Il peut être instancié avec enabled=False pour que
les services existants n'aient jamais à conditionner leurs imports.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collaborative_state import CollabUnlockedCache
from app.models.contact import Contact
from app.repositories.supabase_repository import SupabaseRepository
from app.services.contact_validation_service import ContactValidationService

logger = logging.getLogger(__name__)

# ── Système de paliers ────────────────────────────────────────────────────────
#
# Palier 1 (0→5)   : +5 contacts par contribution (progressif)
# Palier 2 (5→10)  : bonus de +100 contacts à 10 contributions
# Palier 3 (10→20) : bonus de +200 contacts à 20 contributions
# Palier 4 (20→50) : bonus de +500 contacts à 50 contributions
# Palier 5 (50→100): accès illimité à 100 contributions
#
# Chaque tuple : (from_incl, to_excl, next_threshold, reward_label)
TIER_RANGES: tuple[tuple[int, int, int, str], ...] = (
    (0,  5,   5,   "+5 contacts par contribution"),
    (5,  10,  10,  "+100 contacts en bonus"),
    (10, 20,  20,  "+200 contacts en bonus"),
    (20, 50,  50,  "+500 contacts en bonus"),
    (50, 100, 100, "Accès complet illimité"),
)

_FREE_CONTACTS: int = 5
_FULL_ACCESS_THRESHOLD: int = 100


def compute_unlockable(contributions: int) -> int:
    """Total de contacts débloquables selon les paliers atteints.

    Retourne -1 si l'accès est illimité (>= 100 contributions).
    """
    if contributions >= _FULL_ACCESS_THRESHOLD:
        return -1
    total = _FREE_CONTACTS
    total += min(contributions, 5) * 5   # +5 par contribution (palier 1)
    if contributions >= 10:
        total += 100
    if contributions >= 20:
        total += 200
    if contributions >= 50:
        total += 500
    return total


@dataclass
class ContributionResult:
    success: bool
    contact_id: Optional[str]
    credits_awarded: int
    rejection_reason: Optional[str]


@dataclass
class CollabStats:
    total_contacts: int          # contacts dans la base Supabase
    user_unlocked: int           # contacts débloqués par cet utilisateur
    user_contributed: int        # contacts partagés par cet utilisateur
    top_contributors: list[int]  # top 3 anonymisés (nb contributions)


class CollaborativeService:
    def __init__(
        self,
        supabase_repo: SupabaseRepository,
        contact_validation_service: ContactValidationService,
        db: Session,
        user_id: str,
        enabled: bool = False,
    ) -> None:
        self._repo = supabase_repo
        self._validation = contact_validation_service
        self._db = db
        self._user_id = user_id
        self._enabled = enabled

    # ── État ──────────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._enabled

    # ── Crédits ───────────────────────────────────────────────────────────────

    def get_contributions_count(self) -> int:
        """Nombre de contacts contribués par cet utilisateur."""
        if not self._enabled:
            return 0
        return self._repo.get_contributions_count(self._user_id)

    def has_full_access(self) -> bool:
        """True si l'utilisateur a atteint 100 contributions (accès illimité)."""
        return self.get_contributions_count() >= _FULL_ACCESS_THRESHOLD

    def get_credits(self) -> int:
        """Contacts débloquables selon les paliers atteints.

        Retourne -1 si l'accès est illimité (>= 100 contributions).
        """
        if not self._enabled:
            return 0
        return compute_unlockable(self.get_contributions_count())

    def refresh_credits(self) -> int:
        """Alias explicite — force un aller-retour Supabase."""
        return self.get_credits()

    def get_stats(self) -> CollabStats:
        """Récupère les stats de la base collaborative en un seul appel groupé."""
        if not self._enabled:
            return CollabStats(0, 0, 0, [])
        return CollabStats(
            total_contacts=self._repo.get_total_contacts_count(),
            user_unlocked=self._repo.get_unlocked_count(self._user_id),
            user_contributed=self._repo.get_contributions_count(self._user_id),
            top_contributors=self._repo.get_top_contributors(3),
        )

    # ── Contribution ──────────────────────────────────────────────────────────

    def contribute_contact(self, contact: Contact) -> ContributionResult:
        """Valide et contribue un contact à la base collaborative.

        Étapes : validation qualité → upsert Supabase → enregistrement
        contribution → mise à jour flag local.
        Retourne credits_awarded=0 en V1 (l'attribution est côté serveur).
        """
        if not self._enabled:
            return ContributionResult(
                success=False,
                contact_id=None,
                credits_awarded=0,
                rejection_reason="Mode collaboratif désactivé",
            )

        result = self._validation.validate(contact)
        if not result.is_valid:
            return ContributionResult(
                success=False,
                contact_id=None,
                credits_awarded=0,
                rejection_reason=result.rejection_reason,
            )

        if not contact.email:
            return ContributionResult(
                success=False,
                contact_id=None,
                credits_awarded=0,
                rejection_reason="Email manquant",
            )

        # Résolution du nom d'entreprise via la relation SQLAlchemy
        company_name: str | None = None
        if contact.company_id is not None:
            from app.models.company import Company
            company = self._db.get(Company, contact.company_id)
            if company:
                company_name = company.name

        metadata = {
            "first_name": contact.first_name,
            "last_name": contact.last_name,
            "job_title": contact.job_title,
            "company_name": company_name,
            "country": contact.country,
            "linkedin_url": contact.linkedin_url,
            "quality_score": result.score,
        }
        try:
            contact_id = self._repo.upsert_contact(contact.email, metadata)
        except Exception as exc:
            logger.exception("upsert_contact raised pour email=%r", contact.email)
            return ContributionResult(
                success=False,
                contact_id=None,
                credits_awarded=0,
                rejection_reason=f"Upsert échoué : {exc}",
            )
        if not contact_id:
            return ContributionResult(
                success=False,
                contact_id=None,
                credits_awarded=0,
                rejection_reason="Upsert OK mais aucun ID retourné",
            )

        self._repo.create_contribution(self._user_id, contact_id)

        # Marquer le contact local comme contribué
        contact.collab_source_id = contact_id
        contact.collab_is_contributed = True
        self._db.flush()

        return ContributionResult(
            success=True,
            contact_id=contact_id,
            credits_awarded=0,
            rejection_reason=None,
        )

    # ── Déblocage ─────────────────────────────────────────────────────────────

    def unlock_contacts(self, count: int) -> list[dict]:
        """Débloque `count` contacts depuis Supabase et les stocke localement.

        Règles :
        - >= 100 contributions → accès illimité, on peut débloquer `count`.
        - Sinon : budget = 5 (gratuits) + contributions - déjà débloqués.
        """
        if not self._enabled:
            return []

        contributions = self.get_contributions_count()

        if contributions >= _FULL_ACCESS_THRESHOLD:
            effective_count = count
        else:
            already_unlocked = self._repo.get_unlocked_count(self._user_id)
            budget = compute_unlockable(contributions) - already_unlocked
            if budget <= 0:
                logger.warning(
                    "unlock_contacts: budget épuisé (contributions=%d, déjà débloqués=%d)",
                    contributions, already_unlocked,
                )
                return []
            effective_count = min(count, budget)

        contacts = self._repo.request_unlock(self._user_id, effective_count)
        if not contacts:
            return []

        self._store_unlocked_locally(contacts)
        return contacts

    def _store_unlocked_locally(self, contacts: list[dict]) -> None:
        """Insère les contacts débloqués dans collab_unlocked_cache (upsert)."""
        for c in contacts:
            supabase_id = str(c.get("id", ""))
            if not supabase_id:
                continue
            existing = self._db.scalar(
                select(CollabUnlockedCache).where(
                    CollabUnlockedCache.supabase_id == supabase_id
                )
            )
            if existing:
                continue
            row = CollabUnlockedCache(
                supabase_id=supabase_id,
                email=c.get("email_encrypted") or "",  # V2 : déchiffré
                email_hash=c.get("email_hash", ""),
                first_name=c.get("first_name"),
                last_name=c.get("last_name"),
                job_title=c.get("job_title"),
                company_name=c.get("company_name"),
                country=c.get("country"),
                linkedin_url=c.get("linkedin_url"),
                quality_score=c.get("quality_score", 0),
                contact_count=c.get("contact_count", 0),
                unlocked_at=datetime.utcnow(),
            )
            self._db.add(row)
        self._db.flush()

    # ── Synchronisation delta ─────────────────────────────────────────────────

    def sync_unlocked_locally(
        self, last_sync_at: Optional[datetime] = None
    ) -> int:
        """Synchronise les nouveaux contacts débloqués depuis Supabase.

        Retourne le nombre de nouvelles entrées insérées dans
        collab_unlocked_cache.
        """
        if not self._enabled:
            return 0

        remote = self._repo.get_unlocked_contacts(self._user_id, since=last_sync_at)
        if not remote:
            return 0

        # Les résultats incluent le contact jointé sous la clé "contacts"
        raw_contacts = []
        for row in remote:
            contact_data = row.get("contacts")
            if isinstance(contact_data, dict):
                raw_contacts.append(contact_data)

        before = self._db.scalar(
            select(CollabUnlockedCache).where(True)
        )
        self._store_unlocked_locally(raw_contacts)
        after_count = self._db.scalar(
            select(CollabUnlockedCache).where(True)
        )
        # Approximation : on retourne la taille de la liste traitée
        return len(raw_contacts)

    # ── Déduplication ─────────────────────────────────────────────────────────

    def is_already_contacted_by_others(self, email: str) -> bool:
        """Vérifie si un email a déjà été contacté par un autre utilisateur."""
        if not self._enabled:
            return False
        contacted = self._repo.check_already_contacted([email])
        return bool(contacted)

    def filter_already_contacted(self, contacts: list) -> list:
        """Retire de la liste les contacts déjà contactés par d'autres utilisateurs.

        Effectue un seul appel batch vers Supabase pour limiter la latence.
        """
        if not self._enabled or not contacts:
            return contacts

        emails = [c.email for c in contacts if c.email]
        if not emails:
            return contacts

        contacted_hashes = self._repo.check_already_contacted(emails)
        if not contacted_hashes:
            return contacts

        from app.repositories.supabase_repository import _hash_email

        filtered = [
            c for c in contacts
            if not (c.email and _hash_email(c.email) in contacted_hashes)
        ]
        removed = len(contacts) - len(filtered)
        if removed:
            logger.info("filter_already_contacted: %d contact(s) écartés", removed)
        return filtered

    # ── Événements d'envoi ────────────────────────────────────────────────────

    def record_send_event(self, email: str) -> None:
        """Enregistre un événement 'contacted' pour un email."""
        if not self._enabled or not email:
            return
        self._repo.record_contact_event(email, "contacted", self._user_id)

    # ── Import local ──────────────────────────────────────────────────────────

    def import_unlocked_to_local(self) -> int:
        """Copie les entrées non importées de collab_unlocked_cache vers contacts.

        Ne crée pas de doublon si un contact avec le même email existe déjà.
        Retourne le nombre de contacts nouvellement créés.
        """
        if not self._enabled:
            return 0

        pending = self._db.scalars(
            select(CollabUnlockedCache).where(
                CollabUnlockedCache.imported_to_local == False  # noqa: E712
            )
        ).all()

        created = 0
        for cache_row in pending:
            if not cache_row.email:
                cache_row.imported_to_local = True
                continue

            email_lower = cache_row.email.strip().lower()
            exists = self._db.scalar(
                select(Contact).where(Contact.email_normalized == email_lower)
            )
            if not exists:
                contact = Contact(
                    email=cache_row.email,
                    email_normalized=email_lower,
                    first_name=cache_row.first_name,
                    last_name=cache_row.last_name,
                    job_title=cache_row.job_title,
                    country=cache_row.country,
                    linkedin_url=cache_row.linkedin_url,
                    collab_source_id=cache_row.supabase_id,
                    collab_is_contributed=False,
                    source="collab_unlock",
                )
                self._db.add(contact)
                created += 1

            cache_row.imported_to_local = True

        self._db.flush()
        logger.info("import_unlocked_to_local: %d contact(s) créés", created)
        return created
