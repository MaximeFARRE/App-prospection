from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QMimeData, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.db.session import SessionLocal
from app.repositories import import_repository
from app.services import csv_import_service


class _ImportCsvWorker(QThread):
    completed = pyqtSignal(object, str)

    def __init__(self, file_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._file_path = file_path

    def run(self) -> None:
        db = SessionLocal()
        try:
            result = csv_import_service.import_csv(self._file_path, db)
            self.completed.emit(result, "")
        except Exception as exc:  # pragma: no cover - sécurité UI
            self.completed.emit(None, str(exc))
        finally:
            db.close()


class _DropZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _extract_csv_from_mime_data(event.mimeData()) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        file_path = _extract_csv_from_mime_data(event.mimeData())
        if file_path is None:
            event.ignore()
            return
        self.file_dropped.emit(file_path)
        event.acceptProposedAction()


class ImportsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._selected_file: str | None = None
        self._active_worker: _ImportCsvWorker | None = None

        self._build_ui()
        self._load_history()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel("Imports CSV")
        title.setStyleSheet("color: #0f172a; font-size: 24px; font-weight: 700;")
        root.addWidget(title)

        self._drop_zone = _DropZone()
        self._drop_zone.setFrameShape(QFrame.Shape.StyledPanel)
        self._drop_zone.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 2px dashed #94a3b8; border-radius: 8px; }"
        )
        self._drop_zone.file_dropped.connect(self._on_file_dropped)
        zone_layout = QVBoxLayout(self._drop_zone)
        zone_layout.setContentsMargins(16, 16, 16, 16)
        zone_layout.setSpacing(8)

        instruction = QLabel("Glisse-dépose un fichier CSV ici ou utilise le bouton ci-dessous.")
        instruction.setWordWrap(True)
        instruction.setStyleSheet("color: #334155; font-size: 13px;")
        zone_layout.addWidget(instruction)

        self._file_label = QLabel("Aucun fichier sélectionné.")
        self._file_label.setStyleSheet("color: #64748b; font-size: 12px;")
        self._file_label.setWordWrap(True)
        zone_layout.addWidget(self._file_label)
        root.addWidget(self._drop_zone)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._choose_button = QPushButton("Choisir un fichier CSV")
        self._choose_button.clicked.connect(self._choose_file)
        actions.addWidget(self._choose_button)

        self._start_button = QPushButton("Lancer l'import")
        self._start_button.clicked.connect(self._start_import)
        actions.addWidget(self._start_button)

        self._refresh_button = QPushButton("Actualiser l'historique")
        self._refresh_button.clicked.connect(self._load_history)
        actions.addWidget(self._refresh_button)

        help_button = QPushButton("? Colonnes acceptées")
        help_button.setToolTip("Voir la liste des noms de colonnes CSV reconnus par l'import")
        help_button.clicked.connect(self._show_csv_help)
        actions.addWidget(help_button)
        actions.addStretch(1)
        root.addLayout(actions)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        root.addWidget(self._progress)

        self._summary_label = QLabel("Aucun import lancé.")
        self._summary_label.setStyleSheet("color: #475569; font-size: 12px;")
        self._summary_label.setWordWrap(True)
        root.addWidget(self._summary_label)

        self._errors_text = QTextEdit()
        self._errors_text.setReadOnly(True)
        self._errors_text.setFixedHeight(100)
        self._errors_text.setStyleSheet(
            "background: #fff1f2; color: #991b1b; font-size: 11px; border: 1px solid #fca5a5;"
        )
        self._errors_text.setVisible(False)
        root.addWidget(self._errors_text)

        history_title = QLabel("Historique des imports")
        history_title.setStyleSheet("color: #0f172a; font-size: 16px; font-weight: 600;")
        root.addWidget(history_title)

        self._history_table = QTableWidget(0, 4)
        self._history_table.setHorizontalHeaderLabels(["Fichier", "Date", "Créés", "Statut"])
        self._history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._history_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.horizontalHeader().setStretchLastSection(True)
        self._history_table.setAlternatingRowColors(True)
        root.addWidget(self._history_table, stretch=1)

    def _on_file_dropped(self, file_path: str) -> None:
        self._set_selected_file(file_path)
        self._summary_label.setText("Fichier prêt. Clique sur 'Lancer l'import'.")

    def _choose_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choisir un fichier CSV",
            str(Path.cwd()),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not file_path:
            return
        self._set_selected_file(file_path)

    def _set_selected_file(self, file_path: str) -> None:
        self._selected_file = file_path
        self._file_label.setText(f"Fichier sélectionné : {file_path}")

    def _start_import(self) -> None:
        if self._active_worker is not None and self._active_worker.isRunning():
            return
        if not self._selected_file:
            QMessageBox.warning(self, "Import CSV", "Sélectionne d'abord un fichier CSV.")
            return

        if not self._selected_file.lower().endswith(".csv"):
            QMessageBox.warning(self, "Import CSV", "Le fichier doit être au format .csv.")
            return

        self._set_busy_state(True)
        self._summary_label.setText("Import en cours...")

        worker = _ImportCsvWorker(self._selected_file, self)
        worker.completed.connect(self._on_import_completed)
        worker.finished.connect(worker.deleteLater)
        self._active_worker = worker
        worker.start()

    def _on_import_completed(self, result_obj: object, error: str) -> None:
        self._set_busy_state(False)
        self._active_worker = None

        if error:
            self._summary_label.setText(f"Échec de l'import : {error}")
            QMessageBox.critical(self, "Import CSV", f"Erreur pendant l'import:\n{error}")
            self._load_history()
            return

        result = result_obj
        summary = (
            f"{result.created_contacts} contacts créés / "
            f"{result.created_companies} entreprises / "
            f"{result.duplicate_count} doublon / "
            f"{result.error_count} erreur"
        )
        self._summary_label.setText(summary)

        if result.errors:
            self._errors_text.setPlainText("\n".join(result.errors))
            self._errors_text.setVisible(True)
        else:
            self._errors_text.setVisible(False)

        self._load_history()

    def _show_csv_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Colonnes CSV acceptées")
        dialog.setMinimumWidth(640)
        dialog.setMinimumHeight(480)

        vbox = QVBoxLayout(dialog)
        intro = QLabel(
            "L'import reconnaît automatiquement les colonnes ci-dessous (insensible à la casse).\n"
            "Une colonne email est <b>obligatoire</b>. Les autres champs sont optionnels."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        vbox.addWidget(intro)

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Champ", "Noms de colonnes acceptés"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)

        rows = [
            ("Prénom *", "first_name, prospect_first_name, First Name"),
            ("Nom *", "last_name, prospect_last_name, Last Name"),
            ("Nom complet *", "Full Name, prospect_full_name  (fallback si prénom/nom absents)"),
            ("Email *", "email, Work Email, Personal Email, Additional Email 1/2/3,\ncontact_professions_email, contact_emails"),
            ("Entreprise", "Company, prospect_company_name"),
            ("Poste", "job, Title, Headline, prospect_job_title"),
            ("Niveau poste", "prospect_job_level_main"),
            ("Pays", "Country, prospect_country_name"),
            ("Région", "Region, prospect_region_name"),
            ("Ville", "City, prospect_city"),
            ("Localisation", "Location  (format : Ville, Région, Pays)"),
            ("Téléphone", "Phone, Phone 2/3/4, contact_mobile_phone"),
            ("LinkedIn", "Linkedin URL, LinkedIn URL, prospect_linkedin"),
            ("Sexe", "sex, sexe, gender, Gender, prospect_gender, contact_gender"),
            ("Statut email", "Work Email Status, contact_professional_email_status"),
            ("ID prospect", "Prospect ID, prospect_id"),
            ("Site web entreprise", "Company Website, prospect_company_website"),
            ("LinkedIn entreprise", "Company LinkedIn URL, Company Linkedin URL, prospect_company_linkedin"),
        ]

        table.setRowCount(len(rows))
        for i, (field, cols) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(field))
            item = QTableWidgetItem(cols)
            item.setToolTip(cols)
            table.setItem(i, 1, item)
        table.resizeRowsToContents()

        scroll = QScrollArea()
        scroll.setWidget(table)
        scroll.setWidgetResizable(True)
        vbox.addWidget(scroll)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        vbox.addWidget(buttons)
        dialog.exec()

    def _set_busy_state(self, busy: bool) -> None:
        self._choose_button.setEnabled(not busy)
        self._start_button.setEnabled(not busy)
        self._refresh_button.setEnabled(not busy)

        if busy:
            self._progress.setVisible(True)
            self._progress.setRange(0, 0)  # indéterminé pendant traitement
            return

        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._progress.setVisible(False)

    def _load_history(self) -> None:
        db = SessionLocal()
        try:
            jobs = import_repository.get_all(db, {"limit": 200})
        except Exception as exc:  # pragma: no cover - sécurité UI
            self._summary_label.setText(f"Impossible de charger l'historique : {exc}")
            return
        finally:
            db.close()

        self._history_table.setRowCount(len(jobs))
        for row_index, job in enumerate(jobs):
            values = [
                str(job.filename),
                _format_datetime(job.created_at),
                str(job.created_count),
                _format_status(job.status),
            ]
            for col_index, value in enumerate(values):
                self._history_table.setItem(row_index, col_index, QTableWidgetItem(value))

def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return "-"


def _format_status(status: Any) -> str:
    raw = str(status or "").strip().lower()
    mapping = {
        "done": "Terminé",
        "failed": "Échec",
        "processing": "En cours",
        "pending": "En attente",
    }
    return mapping.get(raw, raw or "-")


def _extract_csv_from_mime_data(mime_data: QMimeData) -> str | None:
    if not mime_data.hasUrls():
        return None

    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        local_file = url.toLocalFile()
        if local_file.lower().endswith(".csv"):
            return local_file
    return None
