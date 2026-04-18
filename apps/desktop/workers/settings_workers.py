from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.core.config import GmailAccount
from app.db.session import SessionLocal
from app.services.gmail_sent_contacts_service import _build_service, sync_sent_contacts


class GmailConnectionWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, account_index: int, account: GmailAccount, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._account_index = account_index
        self._account = account

    def run(self) -> None:
        payload: dict[str, Any] = {
            "index": self._account_index,
            "ok": False,
            "error": "",
            "profile": {},
        }
        try:
            service = _build_service(self._account)
            profile = service.users().getProfile(userId="me").execute()
            payload["ok"] = True
            payload["profile"] = profile
        except Exception as exc:  # pragma: no cover - sécurité UI
            payload["error"] = str(exc)
        self.finished.emit(payload)


class GmailSyncWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, since_days: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.since_days: int | None = None if since_days == 0 else since_days

    def run(self) -> None:
        db = SessionLocal()
        try:
            if self.since_days is None:
                self.progress.emit("Synchronisation complète : tous les historiques envoyés.")
            else:
                self.progress.emit(f"Synchronisation limitée aux {self.since_days} derniers jours.")

            result = sync_sent_contacts(db, since_days=self.since_days)
            all_errors: list[str] = []
            for acc in result.accounts:
                self.progress.emit(f"✓ {acc.account_email} : {acc.messages_scanned} mails scannés")
                if acc.errors:
                    self.progress.emit(f"  ⚠ {len(acc.errors)} erreurs")
                    all_errors.extend(acc.errors)

            self.finished.emit(
                {
                    "new_entries": result.total_new_entries,
                    "matched": result.total_contacts_matched,
                    "errors": all_errors,
                }
            )
        except Exception as exc:  # pragma: no cover - sécurité UI
            self.error.emit(str(exc))
        finally:
            db.close()
