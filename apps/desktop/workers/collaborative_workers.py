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
    """Construit un SupabaseRepository à partir de la config .env."""
    from supabase import create_client
    from app.core.config import supabase_settings
    from app.repositories.supabase_repository import SupabaseRepository

    client = create_client(supabase_settings.supabase_url, supabase_settings.supabase_anon_key)
    return SupabaseRepository(client)


def _make_service(repo, db, user_id: str):
    """Instancie un CollaborativeService activé avec injection des dépendances."""
    from app.services.collaborative_service import CollaborativeService
    from app.services.contact_validation_service import ContactValidationService

    return CollaborativeService(
        supabase_repo=repo,
        contact_validation_service=ContactValidationService(),
        db=db,
        user_id=user_id,
        enabled=True,
    )


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
