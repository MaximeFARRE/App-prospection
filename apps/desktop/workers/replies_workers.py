from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.db.session import SessionLocal
from app.services.gmail_sync_service import sync_replies


class RepliesSyncWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(object, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def run(self) -> None:
        db = SessionLocal()
        try:
            self.progress.emit("Synchronisation des reponses Gmail en cours...")
            result = sync_replies(db=db, since_days=30)

            all_errors: list[str] = []
            for account in result.accounts:
                self.progress.emit(
                    f"{account.account_email}: {account.replies_created} nouvelles reponses"
                )
                if account.errors:
                    all_errors.extend(account.errors)

            self.finished.emit(
                {
                    "replies_created": result.total_replies_created,
                    "campaign_states_updated": result.total_campaign_states_updated,
                    "errors": all_errors,
                },
                "",
            )
        except Exception as exc:  # pragma: no cover - securite UI
            self.finished.emit({}, str(exc))
        finally:
            db.close()
