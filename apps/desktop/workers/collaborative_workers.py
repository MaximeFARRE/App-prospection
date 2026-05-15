"""Workers QThread pour les opérations collaboratives Supabase."""
from __future__ import annotations

import dataclasses
import logging
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _make_repo():
    """Construit un SupabaseRepository avec la session authentifiée restaurée."""
    from supabase import create_client
    from app.repositories.supabase_repository import SupabaseRepository
    from services.settings_service import get_supabase_credentials, get_supabase_session

    creds = get_supabase_credentials()
    url = creds.get("supabase_url", "")
    key = creds.get("supabase_anon_key", "")
    if not url or not key:
        raise RuntimeError(
            "URL ou clé Supabase manquante. "
            "Renseignez-les dans Paramètres → Base collaborative."
        )
    session = get_supabase_session()
    access_token = session.get("access_token", "")
    refresh_token = session.get("refresh_token", "")
    logger.debug("_make_repo: access_token présent=%s  refresh_token présent=%s",
                 bool(access_token), bool(refresh_token))

    if not refresh_token:
        raise RuntimeError(
            "Non connecté à Supabase. "
            "Connectez-vous dans Paramètres → Base collaborative."
        )

    # Toujours rafraîchir via le refresh_token pour obtenir un JWT frais.
    # L'access_token stocké peut être expiré ; PostgREST rejetterait
    # silencieusement un token expiré et auth.uid() retournerait NULL.
    client = create_client(url, key)
    try:
        refreshed = client.auth.refresh_session(refresh_token)
        if not refreshed.session:
            raise RuntimeError("Refresh sans session retournée.")
        fresh_access = refreshed.session.access_token
        fresh_refresh = refreshed.session.refresh_token
        from services.settings_service import save_supabase_session
        save_supabase_session(fresh_access, fresh_refresh)
        logger.debug("_make_repo: token rafraîchi, user=%s", refreshed.user.id if refreshed.user else "?")
    except RuntimeError:
        raise
    except Exception as exc:
        logger.warning("_make_repo: refresh échoué (%s) — utilisation du token existant", exc)
        # Fallback : utiliser l'access_token tel quel
        if not access_token:
            raise RuntimeError(
                "Session expirée — reconnectez-vous dans Paramètres → Base collaborative."
            ) from exc
        fresh_access = access_token

    # Injecter le JWT dans les headers PostgREST des deux façons :
    # 1. client.postgrest.auth() → self.headers (utilisé par SyncRequestBuilder)
    # 2. client.postgrest.session.headers → headers httpx de niveau session
    # Les deux sont nécessaires car httpx peut donner priorité aux session headers
    # qui contiennent encore la clé anon définie lors du create_client().
    auth_header = f"Bearer {fresh_access}"
    client.postgrest.auth(fresh_access)
    try:
        client.postgrest.session.headers["Authorization"] = auth_header
        logger.debug("_make_repo: JWT injecté dans self.headers ET session.headers")
    except Exception as exc:
        logger.warning("_make_repo: impossible de forcer session.headers (%s)", exc)
    logger.debug("_make_repo: JWT (token[:30]=%s…)", fresh_access[:30])

    return SupabaseRepository(client)


def _make_service(repo, db, user_id: str, contribution_threshold: int = 0):
    """Instancie un CollaborativeService activé avec injection des dépendances."""
    from app.services.collaborative_service import CollaborativeService
    from app.services.contact_validation_service import ContactValidationService

    return CollaborativeService(
        supabase_repo=repo,
        contact_validation_service=ContactValidationService(threshold=contribution_threshold),
        db=db,
        user_id=user_id,
        enabled=True,
    )


# ── Inscription ───────────────────────────────────────────────────────────────

class SupabaseSignUpWorker(QThread):
    """Crée un compte Supabase Auth depuis l'app, sans passer par le dashboard."""

    signup_success = pyqtSignal(str, str)  # user_id, user_email
    signup_failed = pyqtSignal(str)        # message d'erreur

    def __init__(self, email: str, password: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._email = email
        self._password = password

    def run(self) -> None:
        try:
            repo = _make_repo()
            result = repo.sign_up(self._email, self._password)
            if result:
                access = result.get("access_token") or ""
                refresh = result.get("refresh_token") or ""
                if access and refresh:
                    from services.settings_service import save_supabase_session
                    save_supabase_session(access, refresh)
                # Upsert dans public.users pour satisfaire la FK contact_contributions
                repo.upsert_user(result["user_id"], result["user_email"])
                self.signup_success.emit(result["user_id"], result["user_email"])
            else:
                self.signup_failed.emit("Création de compte échouée — email déjà utilisé ?")
        except Exception as exc:
            logger.exception("SupabaseSignUpWorker failed")
            self.signup_failed.emit(str(exc))


# ── Login ─────────────────────────────────────────────────────────────────────

class SupabaseLoginWorker(QThread):
    """Tente une connexion Supabase et émet le résultat."""

    login_success = pyqtSignal(str, str)  # user_id, user_email
    login_failed = pyqtSignal(str)        # message d'erreur

    def __init__(self, email: str, password: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._email = email
        self._password = password

    def run(self) -> None:
        try:
            repo = _make_repo()
            result = repo.login(self._email, self._password)
            if result:
                access = result.get("access_token") or ""
                refresh = result.get("refresh_token") or ""
                if access and refresh:
                    from services.settings_service import save_supabase_session
                    save_supabase_session(access, refresh)
                # Upsert dans public.users pour satisfaire la FK contact_contributions
                repo.upsert_user(result["user_id"], result["user_email"])
                self.login_success.emit(result["user_id"], result["user_email"])
            else:
                self.login_failed.emit("Email ou mot de passe incorrect")
        except Exception as exc:
            logger.exception("SupabaseLoginWorker failed")
            self.login_failed.emit(str(exc))


# ── Crédits ───────────────────────────────────────────────────────────────────

class SyncCreditsWorker(QThread):
    """Récupère les crédits et le nombre de contributions depuis Supabase.

    Émet (credits, contributions_count) :
    - credits = -1 signifie accès illimité (>= 100 contributions)
    - credits >= 0 sinon (5 gratuits + contributions - déjà débloqués)
    """

    credits_updated = pyqtSignal(int, int)  # credits, contributions_count
    error = pyqtSignal(str)

    def __init__(self, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user_id = user_id

    def run(self) -> None:
        db = SessionLocal()
        try:
            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            contributions = service.get_contributions_count()
            credits = service.get_credits()
            self.credits_updated.emit(credits, contributions)
        except Exception as exc:
            logger.exception("SyncCreditsWorker failed")
            self.error.emit(str(exc))
        finally:
            db.close()


# ── Déblocage ─────────────────────────────────────────────────────────────────

class UnlockContactsWorker(QThread):
    """Demande le déblocage de N contacts et les retourne."""

    contacts_unlocked = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, user_id: str, count: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user_id = user_id
        self._count = count

    def run(self) -> None:
        db = SessionLocal()
        try:
            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            contacts = service.unlock_contacts(self._count)
            db.commit()
            self.contacts_unlocked.emit(contacts)
        except Exception as exc:
            logger.exception("UnlockContactsWorker failed")
            db.rollback()
            self.error.emit(str(exc))
        finally:
            db.close()


# ── Contribution ──────────────────────────────────────────────────────────────

class ContributeContactWorker(QThread):
    """Contribue un contact local à la base collaborative."""

    contribution_done = pyqtSignal(dict)   # ContributionResult converti en dict
    error = pyqtSignal(str)

    def __init__(self, contact_id: int, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._contact_id = contact_id
        self._user_id = user_id

    def run(self) -> None:
        from app.models.contact import Contact

        db = SessionLocal()
        try:
            contact = db.get(Contact, self._contact_id)
            if contact is None:
                self.error.emit(f"Contact introuvable (id={self._contact_id})")
                return

            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            result = service.contribute_contact(contact)
            db.commit()
            self.contribution_done.emit(dataclasses.asdict(result))
        except Exception as exc:
            logger.exception("ContributeContactWorker failed")
            db.rollback()
            self.error.emit(str(exc))
        finally:
            db.close()


# ── Contribution en masse ─────────────────────────────────────────────────────

class BulkContributeWorker(QThread):
    """Contribue tous les contacts locaux non encore partagés vers Supabase."""

    progress = pyqtSignal(int, int)           # done, total
    finished = pyqtSignal(int, int, str)      # contributed, skipped, diagnostic
    error = pyqtSignal(str)

    def __init__(self, user_id: str, limit: Optional[int] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user_id = user_id
        self._limit = limit

    def run(self) -> None:
        from app.models.contact import Contact
        from sqlalchemy import select

        db = SessionLocal()
        try:
            contacts = list(db.scalars(
                select(Contact).where(Contact.collab_is_contributed == False)  # noqa: E712
            ).all())
            if self._limit is not None:
                contacts = contacts[: self._limit]
            total = len(contacts)
            logger.info("BulkContribute: %d contact(s) à traiter (limit=%s)", total, self._limit)

            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            contributed = 0
            skipped = 0
            skip_reasons: dict[str, int] = {}

            for i, contact in enumerate(contacts):
                logger.debug(
                    "Contact #%d id=%s email=%r email_status=%r score_brut=?",
                    i + 1, contact.id, contact.email, contact.email_status,
                )
                result = service.contribute_contact(contact)
                if result.success:
                    contributed += 1
                    logger.debug("  → OK (supabase_id=%s)", result.contact_id)
                else:
                    skipped += 1
                    reason = result.rejection_reason or "inconnu"
                    skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                    logger.warning(
                        "  → SKIP id=%s email=%r raison=%r",
                        contact.id, contact.email, reason,
                    )
                self.progress.emit(i + 1, total)

            db.commit()
            diagnostic = (
                "; ".join(f"{r} ×{n}" for r, n in skip_reasons.items())
                if skip_reasons else ""
            )
            logger.info("BulkContribute terminé: %d OK, %d ignorés. %s", contributed, skipped, diagnostic)
            self.finished.emit(contributed, skipped, diagnostic)
        except Exception as exc:
            logger.exception("BulkContributeWorker failed")
            db.rollback()
            self.error.emit(str(exc))
        finally:
            db.close()


# ── Stats ─────────────────────────────────────────────────────────────────────

class FetchStatsWorker(QThread):
    """Récupère les statistiques de la base collaborative."""

    stats_ready = pyqtSignal(int, int, int, list)  # total, unlocked, contributed, top3
    error = pyqtSignal(str)

    def __init__(self, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user_id = user_id

    def run(self) -> None:
        db = SessionLocal()
        try:
            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            stats = service.get_stats()
            self.stats_ready.emit(
                stats.total_contacts,
                stats.user_unlocked,
                stats.user_contributed,
                stats.top_contributors,
            )
        except Exception as exc:
            logger.exception("FetchStatsWorker failed")
            self.error.emit(str(exc))
        finally:
            db.close()


# ── Import local ──────────────────────────────────────────────────────────────

class ImportUnlockedWorker(QThread):
    """Copie les contacts débloqués depuis le cache vers la table contacts."""

    import_done = pyqtSignal(int)   # nombre de contacts créés
    error = pyqtSignal(str)

    def __init__(self, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user_id = user_id

    def run(self) -> None:
        db = SessionLocal()
        try:
            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            created = service.import_unlocked_to_local()
            db.commit()
            self.import_done.emit(created)
        except Exception as exc:
            logger.exception("ImportUnlockedWorker failed")
            db.rollback()
            self.error.emit(str(exc))
        finally:
            db.close()


class PushContactUpdateWorker(QThread):
    """Pousse la mise à jour d'un contact vers Supabase en arrière-plan.

    Fire-and-forget : aucun signal d'erreur n'est émis vers l'UI.
    À utiliser depuis le thread principal pour les modifications en place
    (changement de sexe inline, etc.) qui ne passent pas par un worker existant.
    """

    def __init__(
        self,
        supabase_id: str,
        fields: dict,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._supabase_id = supabase_id
        self._fields = fields

    def run(self) -> None:
        try:
            repo = _make_repo()
            repo.update_contact_fields(self._supabase_id, self._fields)
        except Exception as exc:
            logger.debug("PushContactUpdateWorker ignoré (id=%s): %s", self._supabase_id, exc)
