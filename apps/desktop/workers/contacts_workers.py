from __future__ import annotations

import logging
from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.contact import Contact
from app.repositories import contact_repository
from app.services.email_verification_service import verify_email_for_send
from app.services.sex_detection_service import detect_contacts_sex

logger = logging.getLogger(__name__)

# Champs autorisés à être synchronisés vers Supabase
_SUPABASE_EDITABLE = {
    "first_name", "last_name", "job_title", "company_name",
    "country", "linkedin_url", "email_status", "sex",
}


def _try_push_to_supabase(supabase_id: str, fields: dict) -> None:
    """Pousse une mise à jour vers Supabase (best-effort, silencieux en cas d'erreur).

    À appeler uniquement depuis un thread worker — jamais depuis le thread UI.
    """
    try:
        from workers.collaborative_workers import _make_repo
        repo = _make_repo()
        repo.update_contact_fields(supabase_id, fields)
    except Exception as exc:
        logger.debug("push_to_supabase ignoré (contact=%s): %s", supabase_id, exc)


class ContactUpdateWorker(QThread):
    finished = pyqtSignal(dict, str)

    def __init__(self, contact_id: int, fields: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._contact_id = contact_id
        self._fields = fields

    def run(self) -> None:
        db = SessionLocal()
        collab_source_id: str | None = None
        push_fields: dict = {}
        try:
            contact = contact_repository.update_contact(db, self._contact_id, self._fields)
            if contact is None:
                self.finished.emit({}, "Contact introuvable.")
                return
            db.commit()
            collab_source_id = contact.collab_source_id
            if collab_source_id:
                push_fields = {k: v for k, v in self._fields.items() if k in _SUPABASE_EDITABLE}
            self.finished.emit({"id": contact.id}, "")
        except Exception as exc:
            db.rollback()
            self.finished.emit({}, str(exc))
            return
        finally:
            db.close()

        if collab_source_id and push_fields:
            _try_push_to_supabase(collab_source_id, push_fields)


class EmailVerificationWorker(QThread):
    """Vérifie les adresses email des contacts non vérifiés via QuickEmailVerification."""

    progress = pyqtSignal(int, int, str)   # (current, total, email)
    finished = pyqtSignal(dict, str)        # ({verified, invalid, errors}, error_msg)

    def __init__(
        self,
        contact_ids: list[int] | None = None,
        force: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        """Si contact_ids est None, vérifie tous les contacts sans email_status.
        Si force=True, ignore le filtre email_status IS NULL."""
        super().__init__(parent)
        self._contact_ids = contact_ids
        self._force = force

    def run(self) -> None:
        db = SessionLocal()
        push_todo: list[tuple[str, str]] = []  # [(supabase_id, email_status)]
        try:
            if self._contact_ids is not None:
                contacts = (
                    db.query(Contact)
                    .filter(Contact.id.in_(self._contact_ids), Contact.email.isnot(None))
                    .all()
                )
            elif self._force:
                contacts = (
                    db.query(Contact)
                    .filter(Contact.email.isnot(None))
                    .order_by(Contact.id)
                    .all()
                )
            else:
                contacts = (
                    db.query(Contact)
                    .filter(
                        Contact.email.isnot(None),
                        Contact.email_status.is_(None),
                    )
                    .order_by(Contact.id)
                    .all()
                )

            total = len(contacts)
            verified = 0
            invalid = 0
            errors = 0

            for idx, contact in enumerate(contacts, start=1):
                self.progress.emit(idx, total, contact.email or "")
                # Capturer avant commit (expire_on_commit=True)
                collab_id = contact.collab_source_id
                try:
                    decision = verify_email_for_send(contact.email or "")
                    now = datetime.now(timezone.utc)
                    new_status = "valid" if decision.can_send else "invalid"
                    contact_repository.update_contact(db, contact.id, {
                        "email_status": new_status,
                        "email_checked_at": now,
                        "email_check_reason": decision.reason or "",
                    })
                    db.commit()
                    if collab_id:
                        push_todo.append((collab_id, new_status))
                    if decision.can_send:
                        verified += 1
                    else:
                        invalid += 1
                except Exception:
                    db.rollback()
                    errors += 1

            self.finished.emit({"verified": verified, "invalid": invalid, "errors": errors}, "")
        except Exception as exc:
            db.rollback()
            self.finished.emit({}, str(exc))
            return
        finally:
            db.close()

        if push_todo:
            try:
                from workers.collaborative_workers import _make_repo
                repo = _make_repo()
                for supabase_id, email_status in push_todo:
                    repo.update_contact_fields(supabase_id, {"email_status": email_status})
            except Exception as exc:
                logger.debug("push email_status ignoré (%d contacts): %s", len(push_todo), exc)


class ContactSexDetectionWorker(QThread):
    finished = pyqtSignal(dict, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        db = SessionLocal()
        push_todo: list[tuple[str, str | None]] = []  # [(supabase_id, sex)]
        try:
            summary = detect_contacts_sex(db, dry_run=False, reset=False)
            db.commit()
            # Collecter les contacts collaboratifs pour sync (avant db.close)
            rows = db.execute(
                select(Contact.collab_source_id, Contact.sex)
                .where(Contact.collab_source_id.isnot(None))
            ).all()
            push_todo = [(row[0], row[1]) for row in rows]
            self.finished.emit(
                {
                    "total_contacts": summary.total_contacts,
                    "updated_contacts": summary.updated_contacts,
                    "unchanged_contacts": summary.unchanged_contacts,
                    "homme_count": summary.homme_count,
                    "femme_count": summary.femme_count,
                    "ambigu_count": summary.ambigu_count,
                },
                "",
            )
        except Exception as exc:  # pragma: no cover - sécurité UI
            db.rollback()
            self.finished.emit({}, str(exc))
            return
        finally:
            db.close()

        if push_todo:
            try:
                from workers.collaborative_workers import _make_repo
                repo = _make_repo()
                for supabase_id, sex in push_todo:
                    repo.update_contact_fields(supabase_id, {"sex": sex})
            except Exception as exc:
                logger.debug("push sex ignoré (%d contacts): %s", len(push_todo), exc)
