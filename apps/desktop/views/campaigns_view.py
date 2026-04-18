from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.contact import Contact
from app.services.campaign_prepare_service import QueuedEmail, prepare_campaign
from app.services.eligibility_service import EligibilityResult
from widgets.campaign_preview_dialog import CampaignPreviewDialog
from workers.campaign_workers import CampaignSendWorker


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates"
_TEMPLATE_STEPS = ("intro", "followup_1", "followup_2")


class CampaignsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._queue: list[QueuedEmail] = []
        self._skipped_rows: list[tuple[str, str, str]] = []
        self._send_worker: CampaignSendWorker | None = None
        self._stop_event: threading.Event | None = None
        self._build_ui()
        self._refresh_template_status()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        left_panel = self._build_prepare_panel()
        right_panel = self._build_results_panel()
        root.addWidget(left_panel)
        root.addWidget(right_panel, stretch=1)

    def _build_prepare_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(400)
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("Préparation")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #0f172a;")
        layout.addWidget(title)

        self._campaign_name_input = QLineEdit()
        self._campaign_name_input.setPlaceholderText("Nom de la campagne")
        layout.addWidget(self._campaign_name_input)

        self._templates_status_label = QLabel("Templates : -")
        self._templates_status_label.setStyleSheet("color: #334155; font-size: 12px;")
        layout.addWidget(self._templates_status_label)

        self._open_templates_button = QPushButton("Ouvrir le dossier templates")
        self._open_templates_button.clicked.connect(self._open_templates_folder)
        layout.addWidget(self._open_templates_button)

        self._dry_run_button = QPushButton("Simuler (dry run)")
        self._dry_run_button.clicked.connect(self._run_dry_run)
        layout.addWidget(self._dry_run_button)

        self._summary_label = QLabel("0 à envoyer · 0 ignorés")
        self._summary_label.setStyleSheet("color: #334155; font-size: 12px; font-weight: 600;")
        layout.addWidget(self._summary_label)

        send_row = QHBoxLayout()
        send_row.setSpacing(8)

        self._send_button = QPushButton("Lancer l'envoi")
        self._send_button.setEnabled(False)
        self._send_button.clicked.connect(self._start_send)
        send_row.addWidget(self._send_button)

        self._stop_button = QPushButton("Stop")
        self._stop_button.setEnabled(False)
        self._stop_button.clicked.connect(self._request_stop)
        send_row.addWidget(self._stop_button)

        layout.addLayout(send_row)
        layout.addStretch(1)
        return panel

    def _build_results_panel(self) -> QWidget:
        panel = QFrame()
        panel.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        tabs = QTabWidget()
        self._queue_table = _make_table(["Prénom", "Entreprise", "Email", "Étape", "Compte expéditeur"])
        self._queue_table.cellDoubleClicked.connect(self._open_preview_from_row)
        tabs.addTab(self._queue_table, "File d'envoi")

        self._skipped_table = _make_table(["Prénom", "Email", "Raison"])
        tabs.addTab(self._skipped_table, "Ignorés")
        layout.addWidget(tabs, stretch=1)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setPlaceholderText("Logs d'envoi...")
        layout.addWidget(self._log_text, stretch=1)
        return panel

    def _refresh_template_status(self) -> None:
        parts: list[str] = []
        for step in _TEMPLATE_STEPS:
            marker = "✓" if (_TEMPLATES_DIR / f"{step}.md").exists() else "✗"
            parts.append(f"{step}.md {marker}")
        self._templates_status_label.setText("Templates : " + " / ".join(parts))

    def _open_templates_folder(self) -> None:
        _TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(_TEMPLATES_DIR)))
        self._refresh_template_status()

    def _run_dry_run(self) -> None:
        campaign_name = self._campaign_name_input.text().strip()
        if not campaign_name:
            QMessageBox.warning(self, "Campagne", "Renseigne un nom de campagne.")
            return

        db = SessionLocal()
        try:
            result = prepare_campaign(campaign_name, db, dry_run=True)
            self._queue = result.queue
            self._skipped_rows = _build_skipped_rows(result.skipped, db)
        except Exception as exc:
            QMessageBox.critical(self, "Dry run", f"Impossible de préparer la campagne:\n{exc}")
            return
        finally:
            db.close()

        self._populate_queue_table()
        self._populate_skipped_table()
        self._summary_label.setText(f"{len(self._queue)} à envoyer · {len(self._skipped_rows)} ignorés")
        self._send_button.setEnabled(bool(self._queue))
        self._append_log("Simulation terminée.")

    def _populate_queue_table(self) -> None:
        self._queue_table.setRowCount(len(self._queue))
        for row, item in enumerate(self._queue):
            values = [
                _first_name(item.contact),
                _company_name(item.contact),
                item.contact.email or "",
                item.step,
                item.account.email,
            ]
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                table_item.setData(0x0100, row)  # UserRole
                self._queue_table.setItem(row, column, table_item)

    def _populate_skipped_table(self) -> None:
        self._skipped_table.setRowCount(len(self._skipped_rows))
        for row, (first_name, email, reason) in enumerate(self._skipped_rows):
            self._skipped_table.setItem(row, 0, QTableWidgetItem(first_name))
            self._skipped_table.setItem(row, 1, QTableWidgetItem(email))
            self._skipped_table.setItem(row, 2, QTableWidgetItem(reason))

    def _start_send(self) -> None:
        if self._send_worker is not None and self._send_worker.isRunning():
            return
        if not self._queue:
            QMessageBox.warning(self, "Campagne", "Lance d'abord un dry run.")
            return
        campaign_name = self._campaign_name_input.text().strip()
        if not campaign_name:
            QMessageBox.warning(self, "Campagne", "Nom de campagne manquant.")
            return
        self._stop_event = threading.Event()
        worker = CampaignSendWorker(
            queue=self._queue,
            campaign_name=campaign_name,
            stop_event=self._stop_event,
            parent=self,
        )
        worker.progress.connect(self._on_send_progress)
        worker.log.connect(self._append_log)
        worker.finished.connect(self._on_send_finished)
        worker.finished.connect(worker.deleteLater)
        self._send_worker = worker
        self._send_button.setEnabled(False)
        self._dry_run_button.setEnabled(False)
        self._stop_button.setEnabled(True)
        self._stop_button.setText("Annuler")
        self._stop_button.setStyleSheet("background-color: #f59e0b; color: #111827; font-weight: 600;")
        self._append_log("Envoi de campagne démarré.")
        worker.start()

    def _on_send_progress(self, sent: int, total: int, contact_name: str) -> None:
        self._summary_label.setText(f"{sent}/{total} envoyés · contact en cours: {contact_name}")

    def _on_send_finished(self, payload_obj: object) -> None:
        payload = dict(payload_obj)
        self._send_worker = None
        self._stop_event = None

        sent = int(payload.get("sent", 0))
        failed = int(payload.get("failed", 0))
        self._append_log(f"Envoi terminé : {sent} envoyés, {failed} échecs.")

        if payload.get("error"):
            QMessageBox.warning(self, "Envoi", f"Erreur durant l'envoi:\n{payload['error']}")

        self._send_button.setEnabled(bool(self._queue))
        self._dry_run_button.setEnabled(True)
        self._stop_button.setEnabled(False)
        self._stop_button.setText("Stop")
        self._stop_button.setStyleSheet("")
        self._summary_label.setText(f"{len(self._queue)} à envoyer · {len(self._skipped_rows)} ignorés")

    def _request_stop(self) -> None:
        if self._send_worker is None or not self._send_worker.isRunning() or self._stop_event is None:
            return
        answer = QMessageBox.question(
            self,
            "Annuler l'envoi",
            "L'envoi en cours sera terminé puis la campagne s'arrêtera. Continuer ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._stop_event.set()
        self._append_log("Annulation demandée. Arrêt après l'envoi en cours.")

    def _open_preview_from_row(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self._queue):
            return
        item = self._queue[row]
        CampaignPreviewDialog(item.subject, item.body, self).exec()

    def _append_log(self, line: str) -> None:
        self._log_text.append(line)


def _make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def _first_name(contact: Contact) -> str:
    return str(contact.first_name or "").strip()


def _company_name(contact: Contact) -> str:
    company = getattr(contact, "company", None)
    if company is None:
        return ""
    return str(getattr(company, "name", "") or "").strip()


def _build_skipped_rows(skipped: list[EligibilityResult], db: Session) -> list[tuple[str, str, str]]:
    contact_ids = [result.contact_id for result in skipped]
    if not contact_ids:
        return []

    contacts = db.query(Contact.id, Contact.first_name, Contact.email).filter(Contact.id.in_(contact_ids)).all()
    contact_map = {
        contact_id: (str(first_name or "").strip(), str(email or "").strip())
        for contact_id, first_name, email in contacts
    }
    rows: list[tuple[str, str, str]] = []
    for result in skipped:
        first_name, email = contact_map.get(result.contact_id, ("", ""))
        rows.append((first_name, email, result.reason))
    return rows
