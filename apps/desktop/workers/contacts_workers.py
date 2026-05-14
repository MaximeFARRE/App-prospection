from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.db.session import SessionLocal
from app.repositories import contact_repository
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
