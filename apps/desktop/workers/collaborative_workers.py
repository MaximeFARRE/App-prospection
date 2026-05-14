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
    client = create_client(url, key)

    session = get_supabase_session()
    access_token = session.get("access_token", "")
    refresh_token = session.get("refresh_token", "")
    if not access_token and not refresh_token:
        raise RuntimeError(
            "Non connecté à Supabase. "
            "Connectez-vous dans Paramètres → Base collaborative."
        )
    try:
        client.auth.set_session(access_token, refresh_token)
    except Exception:
        # Access token expiré — tenter un refresh via le refresh token
        try:
            refreshed = client.auth.refresh_session(refresh_token)
            if refreshed.session:
                from services.settings_service import save_supabase_session
                save_supabase_session(
                    refreshed.session.access_token,
                    refreshed.session.refresh_token,
                )
                client.auth.set_session(
                    refreshed.session.access_token,
                    refreshed.session.refresh_token,
                )
            else:
                raise RuntimeError(
                    "Session expirée — reconnectez-vous dans Paramètres → Base collaborative."
                )
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                "Session expirée — reconnectez-vous dans Paramètres → Base collaborative."
            ) from exc

    return SupabaseRepository(client)


def _make_service(repo, db, user_id: str, contribution_threshold: int = 40):
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
                self.login_success.emit(result["user_id"], result["user_email"])
            else:
                self.login_failed.emit("Email ou mot de passe incorrect")
        except Exception as exc:
            logger.exception("SupabaseLoginWorker failed")
            self.login_failed.emit(str(exc))


# ── Crédits ───────────────────────────────────────────────────────────────────

class SyncCreditsWorker(QThread):
    """Récupère les crédits depuis Supabase et les émet."""

    credits_updated = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, user_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._user_id = user_id

    def run(self) -> None:
        db = SessionLocal()
        try:
            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            credits = service.get_credits()
            self.credits_updated.emit(credits)
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

    progress = pyqtSignal(int, int)      # done, total
    finished = pyqtSignal(int, int)      # contributed, skipped
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
            repo = _make_repo()
            service = _make_service(repo, db, self._user_id)
            contributed = 0
            skipped = 0
            for i, contact in enumerate(contacts):
                result = service.contribute_contact(contact)
                if result.success:
                    contributed += 1
                else:
                    skipped += 1
                self.progress.emit(i + 1, total)
            db.commit()
            self.finished.emit(contributed, skipped)
        except Exception as exc:
            logger.exception("BulkContributeWorker failed")
            db.rollback()
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
