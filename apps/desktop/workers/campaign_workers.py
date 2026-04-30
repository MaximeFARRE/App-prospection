from __future__ import annotations

import threading
from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QWidget

from app.db.session import SessionLocal
from app.services.campaign_prepare_service import QueuedEmail
from app.services.mail_send_service import SendProgress, send_campaign


class CampaignSendWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(dict)

    def __init__(
        self,
        queue: list[QueuedEmail],
        campaign_name: str,
        stop_event: threading.Event | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.queue = queue
        self.campaign_name = campaign_name
        self.stop_event = stop_event or threading.Event()

    def run(self) -> None:
        db = SessionLocal()
        previous_sent = 0
        previous_failed = 0

        def _on_progress(state: SendProgress) -> None:
            nonlocal previous_sent, previous_failed
            self.progress.emit(state.sent, state.total, state.current_contact)

            prefix = "•"
            if state.sent > previous_sent:
                prefix = "✓"
            if state.failed > previous_failed:
                prefix = "✗"

            previous_sent = state.sent
            previous_failed = state.failed
            self.log.emit(f"{_now_hms()} {prefix} {state.current_contact}")

        try:
            result = send_campaign(
                queue=self.queue,
                db=db,
                campaign_name=self.campaign_name,
                progress_callback=_on_progress,
                log_callback=lambda line: self.log.emit(f"{_now_hms()} {line}"),
                stop_event=self.stop_event,
            )
            self.finished.emit({"sent": result.sent, "failed": result.failed})
        except Exception as exc:  # pragma: no cover - sécurité UI
            self.log.emit(f"{_now_hms()} ✗ Erreur fatale: {exc}")
            self.finished.emit({"sent": 0, "failed": 0, "error": str(exc)})
        finally:
            db.close()


def _now_hms() -> str:
    return datetime.now().strftime("%H:%M:%S")
