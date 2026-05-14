from __future__ import annotations

from datetime import datetime, timezone

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.db.session import SessionLocal
from app.models.contact import Contact
from app.repositories import contact_repository
from app.services.email_verification_service import verify_email_for_send
from app.services.sex_detection_service import detect_contacts_sex


class ContactUpdateWorker(QThread):
    finished = pyqtSignal(dict, str)

    def __init__(self, contact_id: int, fields: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._contact_id = contact_id
        self._fields = fields

    def run(self) -> None:
        db = SessionLocal()
        try:
            contact = contact_repository.update_contact(db, self._contact_id, self._fields)
            if contact is None:
                self.finished.emit({}, "Contact introuvable.")
                return
            db.commit()
            self.finished.emit({"id": contact.id}, "")
        except Exception as exc:
            db.rollback()
            self.finished.emit({}, str(exc))
        finally:
            db.close()


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
        finally:
            db.close()


class ContactSexDetectionWorker(QThread):
    finished = pyqtSignal(dict, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        db = SessionLocal()
        try:
            summary = detect_contacts_sex(db, dry_run=False, reset=False)
            db.commit()
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
        finally:
            db.close()
