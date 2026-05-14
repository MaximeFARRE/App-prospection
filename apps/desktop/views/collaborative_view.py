"""Onglet base collaborative — crédits, déblocage et import de contacts."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.settings_service import get_collaborative_config, save_collaborative_config
from workers.collaborative_workers import (
    ImportUnlockedWorker,
    SyncCreditsWorker,
    UnlockContactsWorker,
)


class CollaborativeView(QWidget):
    """Vue principale du mode collaboratif.

    Affiche les crédits, permet de débloquer des contacts et de les importer
    dans la base locale.
    """

    credits_updated = pyqtSignal(int)

    def __init__(self) -> None:
        super().__init__()
        self._credits_worker: SyncCreditsWorker | None = None
        self._unlock_worker: UnlockContactsWorker | None = None
        self._import_worker: ImportUnlockedWorker | None = None
        self._build_ui()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(16, 16, 16, 16)
        content.setSpacing(12)

        title = QLabel("Base collaborative")
        title.setStyleSheet("color: #0f172a; font-size: 24px; font-weight: 700;")
        content.addWidget(title)

        content.addWidget(self._build_credits_section())
        content.addWidget(self._build_actions_section())
        content.addWidget(self._build_contacts_table())
        content.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _build_credits_section(self) -> QGroupBox:
        group = QGroupBox("Crédits")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        self._credits_bar = QProgressBar()
        self._credits_bar.setRange(0, 100)
        self._credits_bar.setValue(0)
        self._credits_bar.setFormat("%v crédits")
        self._credits_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._credits_bar)

        self._credits_label = QLabel("0 crédits")
        layout.addWidget(self._credits_label)

        refresh_btn = QPushButton("↻ Rafraîchir")
        refresh_btn.setFixedWidth(110)
        refresh_btn.clicked.connect(self._sync_credits)
        layout.addWidget(refresh_btn)

        return group

    def _build_actions_section(self) -> QGroupBox:
        group = QGroupBox("Actions")
        layout = QHBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        unlock_label = QLabel("Débloquer")
        layout.addWidget(unlock_label)

        self._unlock_spin = QSpinBox()
        self._unlock_spin.setRange(1, 50)
        self._unlock_spin.setValue(5)
        self._unlock_spin.setFixedWidth(70)
        layout.addWidget(self._unlock_spin)

        unlock_btn = QPushButton("contacts")
        unlock_btn.setFixedWidth(140)
        unlock_btn.clicked.connect(self._unlock_contacts)
        layout.addWidget(unlock_btn)
        self._unlock_btn = unlock_btn

        layout.addStretch()

        import_btn = QPushButton("Importer dans mes contacts")
        import_btn.clicked.connect(self._import_unlocked)
        layout.addWidget(import_btn)
        self._import_btn = import_btn

        return group

    def _build_contacts_table(self) -> QGroupBox:
        group = QGroupBox("Contacts débloqués")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Prénom", "Nom", "Société", "Pays", "Statut"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        return group

    # ── Rafraîchissement au focus ─────────────────────────────────────────────

    def refresh(self) -> None:
        self._sync_credits()
        self._load_cached_contacts()

    # ── Crédits ───────────────────────────────────────────────────────────────

    def _sync_credits(self) -> None:
        if self._credits_worker and self._credits_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            return
        worker = SyncCreditsWorker(str(user_id), self)
        worker.credits_updated.connect(self._on_credits_updated)
        worker.error.connect(lambda msg: self._credits_label.setText(f"Erreur : {msg}"))
        worker.credits_updated.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._credits_worker = worker
        worker.start()

    def _on_credits_updated(self, credits: int) -> None:
        self._credits_worker = None
        self._credits_bar.setValue(min(credits, self._credits_bar.maximum()))
        self._credits_label.setText(f"{credits} crédits")
        save_collaborative_config({"credits": credits})
        self.credits_updated.emit(credits)

    # ── Déblocage ─────────────────────────────────────────────────────────────

    def _unlock_contacts(self) -> None:
        if self._unlock_worker and self._unlock_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            QMessageBox.warning(self, "Non connecté", "Connectez-vous dans les paramètres.")
            return
        count = self._unlock_spin.value()
        self._unlock_btn.setEnabled(False)
        worker = UnlockContactsWorker(str(user_id), count, self)
        worker.contacts_unlocked.connect(self._on_contacts_unlocked)
        worker.error.connect(self._on_unlock_error)
        worker.contacts_unlocked.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._unlock_worker = worker
        worker.start()

    def _on_contacts_unlocked(self, contacts: list) -> None:
        self._unlock_worker = None
        self._unlock_btn.setEnabled(True)
        self._load_cached_contacts()
        self._sync_credits()
        QMessageBox.information(
            self, "Déblocage", f"{len(contacts)} contact(s) débloqué(s) avec succès."
        )

    def _on_unlock_error(self, message: str) -> None:
        self._unlock_worker = None
        self._unlock_btn.setEnabled(True)
        QMessageBox.critical(self, "Erreur déblocage", message)

    # ── Import local ──────────────────────────────────────────────────────────

    def _import_unlocked(self) -> None:
        if self._import_worker and self._import_worker.isRunning():
            return
        cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        if not user_id:
            QMessageBox.warning(self, "Non connecté", "Connectez-vous dans les paramètres.")
            return
        self._import_btn.setEnabled(False)
        worker = ImportUnlockedWorker(str(user_id), self)
        worker.import_done.connect(self._on_import_done)
        worker.error.connect(self._on_import_error)
        worker.import_done.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._import_worker = worker
        worker.start()

    def _on_import_done(self, created: int) -> None:
        self._import_worker = None
        self._import_btn.setEnabled(True)
        self._load_cached_contacts()
        QMessageBox.information(
            self, "Import", f"{created} nouveau(x) contact(s) importé(s) dans vos contacts."
        )

    def _on_import_error(self, message: str) -> None:
        self._import_worker = None
        self._import_btn.setEnabled(True)
        QMessageBox.critical(self, "Erreur import", message)

    # ── Chargement du cache local ─────────────────────────────────────────────

    def _load_cached_contacts(self) -> None:
        """Affiche les contacts débloqués depuis collab_unlocked_cache."""
        from app.db.session import SessionLocal
        from app.models.collaborative_state import CollabUnlockedCache
        from sqlalchemy import select

        db = SessionLocal()
        try:
            rows = db.scalars(select(CollabUnlockedCache).order_by(
                CollabUnlockedCache.unlocked_at.desc()
            )).all()
        finally:
            db.close()

        self._table.setRowCount(len(rows))
        group_title = f"Contacts débloqués ({len(rows)})"
        parent_group = self._table.parent()
        if isinstance(parent_group, QGroupBox):
            parent_group.setTitle(group_title)

        for row_idx, row in enumerate(rows):
            self._table.setItem(row_idx, 0, QTableWidgetItem(row.first_name or ""))
            self._table.setItem(row_idx, 1, QTableWidgetItem(row.last_name or ""))
            self._table.setItem(row_idx, 2, QTableWidgetItem(row.company_name or ""))
            self._table.setItem(row_idx, 3, QTableWidgetItem(row.country or ""))
            status = "✓ Importé" if row.imported_to_local else "En attente"
            item = QTableWidgetItem(status)
            item.setForeground(
                Qt.GlobalColor.darkGreen if row.imported_to_local else Qt.GlobalColor.gray
            )
            self._table.setItem(row_idx, 4, item)
