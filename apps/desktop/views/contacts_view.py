from __future__ import annotations

from math import ceil
from typing import Any

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from PyQt6.QtGui import QColor

from app.db.session import SessionLocal
from app.repositories import contact_repository
from workers.contacts_workers import ContactSexDetectionWorker, ContactUpdateWorker, EmailVerificationWorker
from widgets.manual_contact_dialog import ManualContactDialog, ManualContactPayload


PAGE_SIZE = 100
SEX_VALUES = ("homme", "femme")


class _ContactsPageLoader(QThread):
    loaded = pyqtSignal(int, object, int, str)

    def __init__(self, request_id: int, filters: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request_id = request_id
        self._filters = filters

    def run(self) -> None:
        db = SessionLocal()
        try:
            total = contact_repository.count(db, self._filters)
            contacts = contact_repository.get_all(db, self._filters)
            rows = [_contact_to_row(contact) for contact in contacts]
            self.loaded.emit(self._request_id, rows, total, "")
        except Exception as exc:  # pragma: no cover - sécurité UI
            self.loaded.emit(self._request_id, [], 0, str(exc))
        finally:
            db.close()


class ContactsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._current_page = 1
        self._total_contacts = 0
        self._rows: list[dict[str, Any]] = []
        self._request_id = 0
        self._active_loader: _ContactsPageLoader | None = None
        self._sex_detection_worker: ContactSexDetectionWorker | None = None
        self._email_verification_worker: EmailVerificationWorker | None = None
        self._is_rendering = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(250)
        self._debounce_timer.timeout.connect(self._reload_first_page)

        self._build_ui()
        self._connect_signals()
        self._load_page()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Recherche (nom, email, entreprise)")
        filters_row.addWidget(self._search_input, stretch=2)

        self._country_input = QLineEdit()
        self._country_input.setPlaceholderText("Pays")
        filters_row.addWidget(self._country_input, stretch=1)

        self._email_status_filter = QComboBox()
        self._email_status_filter.addItem("Statut email: Tous", None)
        self._email_status_filter.addItem("✓ Valide", "valid")
        self._email_status_filter.addItem("✗ Invalide", "invalid")
        self._email_status_filter.addItem("? Non vérifié", "__missing__")
        filters_row.addWidget(self._email_status_filter, stretch=1)

        self._blocked_filter = QComboBox()
        self._blocked_filter.addItem("Bloqué: Tous", None)
        self._blocked_filter.addItem("Oui", "blocked")
        self._blocked_filter.addItem("Non", "active")
        filters_row.addWidget(self._blocked_filter, stretch=1)

        self._contacted_filter = QComboBox()
        self._contacted_filter.addItem("Contacté: Tous", None)
        self._contacted_filter.addItem("Oui", "contacted")
        self._contacted_filter.addItem("Non", "not_contacted")
        filters_row.addWidget(self._contacted_filter, stretch=1)

        root.addLayout(filters_row)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)
        actions_row.addStretch(1)

        self._detect_sex_button = QPushButton("Détecter les sexes")
        actions_row.addWidget(self._detect_sex_button)

        self._verify_emails_button = QPushButton("Vérifier emails non vérifiés")
        self._verify_emails_button.setToolTip(
            "Vérifie via QuickEmailVerification tous les contacts sans statut email.\n"
            "Nécessite une clé API configurée dans Paramètres."
        )
        actions_row.addWidget(self._verify_emails_button)

        self._reverify_emails_button = QPushButton("Re-vérifier la sélection")
        self._reverify_emails_button.setToolTip(
            "Relance la vérification email pour les contacts sélectionnés,\n"
            "même s'ils ont déjà un statut email."
        )
        actions_row.addWidget(self._reverify_emails_button)

        self._block_contact_button = QPushButton("Bloquer / Débloquer")
        actions_row.addWidget(self._block_contact_button)

        self._add_contact_button = QPushButton("Ajouter un contact")
        actions_row.addWidget(self._add_contact_button)

        root.addLayout(actions_row)

        self._table = QTableWidget(0, 10)
        self._table.setHorizontalHeaderLabels(
            [
                "Prénom",
                "Nom",
                "Sexe",
                "Entreprise",
                "Poste",
                "Email",
                "Pays",
                "Statut email",
                "Déjà contacté",
                "Bloqué",
            ]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.SelectedClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        root.addWidget(self._table, stretch=1)

        footer = QHBoxLayout()
        footer.setSpacing(8)

        self._status_label = QLabel("Chargement...")
        self._status_label.setStyleSheet("color: #64748b;")
        footer.addWidget(self._status_label, stretch=1)

        self._prev_button = QPushButton("← Page précédente")
        self._next_button = QPushButton("Page suivante →")
        self._page_label = QLabel("Page 1 / 1")

        footer.addWidget(self._prev_button)
        footer.addWidget(self._page_label)
        footer.addWidget(self._next_button)
        root.addLayout(footer)

    def _connect_signals(self) -> None:
        self._search_input.textChanged.connect(self._schedule_reload)
        self._country_input.textChanged.connect(self._schedule_reload)
        self._email_status_filter.currentIndexChanged.connect(self._schedule_reload)
        self._blocked_filter.currentIndexChanged.connect(self._schedule_reload)
        self._contacted_filter.currentIndexChanged.connect(self._schedule_reload)
        self._detect_sex_button.clicked.connect(self._start_sex_detection)
        self._verify_emails_button.clicked.connect(self._start_email_verification)
        self._reverify_emails_button.clicked.connect(self._start_force_email_verification)
        self._block_contact_button.clicked.connect(self._block_selected_contact)
        self._add_contact_button.clicked.connect(self._open_add_contact_dialog)
        self._prev_button.clicked.connect(self._go_prev_page)
        self._next_button.clicked.connect(self._go_next_page)
        self._table.cellClicked.connect(self._on_name_cell_clicked)
        self._table.itemChanged.connect(self._on_table_item_changed)
        self._table.cellDoubleClicked.connect(self._open_contact_detail)

    def _schedule_reload(self, *_args: Any) -> None:
        self._debounce_timer.start()

    def _reload_first_page(self) -> None:
        self._current_page = 1
        self._load_page()

    def _go_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._load_page()

    def _go_next_page(self) -> None:
        total_pages = max(1, ceil(self._total_contacts / PAGE_SIZE))
        if self._current_page < total_pages:
            self._current_page += 1
            self._load_page()

    def _load_page(self) -> None:
        filters = self._build_filters()
        filters["page"] = self._current_page
        filters["page_size"] = PAGE_SIZE

        self._set_loading_state(True)
        self._request_id += 1

        loader = _ContactsPageLoader(self._request_id, filters, self)
        loader.loaded.connect(self._on_page_loaded)
        loader.finished.connect(loader.deleteLater)
        self._active_loader = loader
        loader.start()

    def _on_page_loaded(self, request_id: int, rows: object, total: int, error: str) -> None:
        if request_id != self._request_id:
            return

        self._set_loading_state(False)

        if error:
            self._rows = []
            self._total_contacts = 0
            self._table.setRowCount(0)
            self._status_label.setText("Erreur lors du chargement des contacts.")
            QMessageBox.critical(self, "Erreur", f"Impossible de charger les contacts:\n{error}")
            self._update_pagination_controls()
            return

        self._rows = list(rows)
        self._total_contacts = total

        total_pages = max(1, ceil(self._total_contacts / PAGE_SIZE))
        if self._current_page > total_pages:
            self._current_page = total_pages
            self._load_page()
            return

        self._render_rows()
        self._update_pagination_controls()

    def _render_rows(self) -> None:
        self._is_rendering = True
        self._table.setRowCount(len(self._rows))

        for row_index, row in enumerate(self._rows):
            cells = [
                (0, row["first_name"]),
                (1, row["last_name"]),
                (3, row["company_name"]),
                (4, row["job_title"]),
                (5, row["email"]),
                (6, row["country"]),
                (7, row["email_status"]),
                (8, "Oui" if row["has_been_contacted"] else "Non"),
                (9, "Oui" if row["is_blocked"] else "Non"),
            ]

            for col_index, value in cells:
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if col_index not in {0, 1}:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_index in {8, 9}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_index == 7:  # colonne "Statut email"
                    if value == "valid":
                        item.setForeground(QColor("#27ae60"))
                    elif value == "invalid":
                        item.setForeground(QColor("#e74c3c"))
                    else:
                        item.setForeground(QColor("#95a5a6"))
                if row.get("notes"):
                    item.setToolTip(str(row["notes"]))
                self._table.setItem(row_index, col_index, item)

            sex_combo = QComboBox()
            sex_combo.addItem("-", None)
            for sex in SEX_VALUES:
                sex_combo.addItem(sex, sex)
            current_sex = row["sex"] if row["sex"] in SEX_VALUES else None
            sex_combo.setCurrentIndex(0 if current_sex is None else SEX_VALUES.index(current_sex) + 1)
            sex_combo.currentIndexChanged.connect(
                lambda _index, contact_id=row["id"], combo=sex_combo: self._on_sex_changed(contact_id, combo)
            )
            self._table.setCellWidget(row_index, 2, sex_combo)

        self._is_rendering = False
        self._status_label.setText(f"{self._total_contacts} contact(s)")

    def refresh(self) -> None:
        self._load_page()

    def _update_pagination_controls(self) -> None:
        total_pages = max(1, ceil(self._total_contacts / PAGE_SIZE))
        self._page_label.setText(f"Page {self._current_page} / {total_pages}")
        self._prev_button.setEnabled(self._current_page > 1)
        self._next_button.setEnabled(self._current_page < total_pages)

    def _set_loading_state(self, loading: bool) -> None:
        self._table.setEnabled(not loading)
        self._prev_button.setEnabled(not loading and self._current_page > 1)
        self._next_button.setEnabled(not loading)
        if loading:
            self._status_label.setText("Chargement...")

    def _build_filters(self) -> dict[str, Any]:
        filters: dict[str, Any] = {}

        query = self._search_input.text().strip()
        if query:
            filters["query"] = query

        country = self._country_input.text().strip()
        if country:
            filters["country"] = country

        email_status = self._email_status_filter.currentData()
        if email_status:
            filters["email_status"] = email_status

        blocked = self._blocked_filter.currentData()
        if blocked:
            filters["status"] = blocked

        contacted = self._contacted_filter.currentData()
        if contacted:
            filters["contacted"] = contacted

        return filters

    def _on_sex_changed(self, contact_id: int, combo: QComboBox) -> None:
        if self._is_rendering:
            return

        row_index = self._row_index_for_contact(contact_id)
        if row_index < 0:
            return

        sex_data = combo.currentData()
        next_value = str(sex_data).strip().lower() if sex_data else None
        current_value = self._rows[row_index]["sex"] or None
        if current_value == next_value:
            return

        if not self._persist_sex(contact_id, next_value):
            combo.blockSignals(True)
            if current_value is None:
                combo.setCurrentIndex(0)
            else:
                combo.setCurrentIndex(SEX_VALUES.index(current_value) + 1)
            combo.blockSignals(False)
            return

        self._rows[row_index]["sex"] = next_value or ""

    def _on_name_cell_clicked(self, row_index: int, column_index: int) -> None:
        if self._is_rendering:
            return
        if column_index not in {0, 1}:
            return
        item = self._table.item(row_index, column_index)
        if item is not None:
            self._table.editItem(item)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._is_rendering:
            return

        column_index = item.column()
        if column_index not in {0, 1}:
            return

        row_index = item.row()
        if row_index < 0 or row_index >= len(self._rows):
            return

        field = "first_name" if column_index == 0 else "last_name"
        current_value = str(self._rows[row_index].get(field, "") or "").strip()
        next_value = item.text().strip()
        if next_value == current_value:
            return

        contact_id = int(self._rows[row_index]["id"])
        next_first_name = next_value if field == "first_name" else str(self._rows[row_index]["first_name"] or "")
        next_last_name = next_value if field == "last_name" else str(self._rows[row_index]["last_name"] or "")

        if not self._persist_names(contact_id, next_first_name, next_last_name):
            self._table.blockSignals(True)
            item.setText(current_value)
            self._table.blockSignals(False)
            return

        self._rows[row_index]["first_name"] = next_first_name
        self._rows[row_index]["last_name"] = next_last_name
        self._status_label.setText("Nom mis à jour.")

    def _persist_sex(self, contact_id: int, sex: str | None) -> bool:
        db = SessionLocal()
        try:
            contact = contact_repository.set_sex(db, contact_id=contact_id, sex=sex)
            if contact is None:
                QMessageBox.warning(self, "Contact", "Contact introuvable.")
                return False
            db.commit()
            self._status_label.setText("Sexe mis à jour.")
            return True
        except Exception as exc:
            db.rollback()
            QMessageBox.warning(self, "Contact", f"Impossible de mettre à jour le sexe:\n{exc}")
            return False
        finally:
            db.close()

    def _persist_names(self, contact_id: int, first_name: str, last_name: str) -> bool:
        db = SessionLocal()
        try:
            contact = contact_repository.set_names(
                db,
                contact_id=contact_id,
                first_name=first_name,
                last_name=last_name,
            )
            if contact is None:
                QMessageBox.warning(self, "Contact", "Contact introuvable.")
                return False
            db.commit()
            return True
        except Exception as exc:
            db.rollback()
            QMessageBox.warning(self, "Contact", f"Impossible de mettre à jour le nom:\n{exc}")
            return False
        finally:
            db.close()

    def _row_index_for_contact(self, contact_id: int) -> int:
        for index, row in enumerate(self._rows):
            if row["id"] == contact_id:
                return index
        return -1

    def _start_email_verification(self) -> None:
        if self._email_verification_worker is not None and self._email_verification_worker.isRunning():
            return

        answer = QMessageBox.question(
            self,
            "Vérification des emails",
            "Lancer la vérification de tous les contacts sans statut email ?\n"
            "(Nécessite une clé QuickEmailVerification configurée dans Paramètres.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        worker = EmailVerificationWorker(parent=self)
        worker.progress.connect(self._on_email_verification_progress)
        worker.finished.connect(self._on_email_verification_finished)
        worker.finished.connect(worker.deleteLater)
        self._email_verification_worker = worker
        self._verify_emails_button.setEnabled(False)
        self._reverify_emails_button.setEnabled(False)
        self._status_label.setText("Vérification des emails en cours…")
        worker.start()

    def _on_email_verification_progress(self, current: int, total: int, email: str) -> None:
        self._status_label.setText(f"Vérification {current}/{total} : {email}")

    def _start_force_email_verification(self) -> None:
        if self._email_verification_worker is not None and self._email_verification_worker.isRunning():
            return

        selected_row_indices = sorted({idx.row() for idx in self._table.selectionModel().selectedRows()})
        selected_row_indices = [i for i in selected_row_indices if 0 <= i < len(self._rows)]

        if not selected_row_indices:
            QMessageBox.warning(self, "Re-vérifier emails", "Sélectionne d'abord des contacts dans la table.")
            return

        contact_ids = [int(self._rows[i]["id"]) for i in selected_row_indices]

        worker = EmailVerificationWorker(contact_ids=contact_ids, force=True, parent=self)
        worker.progress.connect(self._on_email_verification_progress)
        worker.finished.connect(self._on_email_verification_finished)
        worker.finished.connect(worker.deleteLater)
        self._email_verification_worker = worker
        self._reverify_emails_button.setEnabled(False)
        self._verify_emails_button.setEnabled(False)
        self._status_label.setText(f"Re-vérification de {len(contact_ids)} contact(s) en cours…")
        worker.start()

    def _on_email_verification_finished(self, payload: dict, error: str) -> None:
        self._verify_emails_button.setEnabled(True)
        self._reverify_emails_button.setEnabled(True)
        self._email_verification_worker = None

        if error:
            QMessageBox.warning(self, "Vérification des emails", f"Erreur : {error}")
            self._status_label.setText("Vérification échouée.")
            return

        verified = int(payload.get("verified", 0))
        invalid = int(payload.get("invalid", 0))
        errors = int(payload.get("errors", 0))
        self._status_label.setText(
            f"Vérification terminée : {verified} valides, {invalid} invalides, {errors} erreurs."
        )
        self._reload_first_page()

    def _open_add_contact_dialog(self) -> None:
        dialog = ManualContactDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.payload()
        if not self._create_manual_contact(payload):
            return

        self._status_label.setText("Contact ajouté.")
        self._reload_first_page()

    def _create_manual_contact(self, payload: ManualContactPayload) -> bool:
        db = SessionLocal()
        try:
            contact_repository.create_manual_contact(
                db,
                first_name=payload.first_name,
                last_name=payload.last_name,
                email=payload.email,
                company_name=payload.company_name,
                job_title=payload.job_title,
                sex=payload.sex,
                country=payload.country,
                city=payload.city,
                phone=payload.phone,
                linkedin_url=payload.linkedin_url,
                notes=payload.notes,
                source="manual",
            )
            db.commit()
            return True
        except ValueError as exc:
            db.rollback()
            QMessageBox.warning(self, "Ajouter un contact", str(exc))
            return False
        except Exception as exc:
            db.rollback()
            QMessageBox.warning(self, "Ajouter un contact", f"Impossible de créer le contact:\n{exc}")
            return False
        finally:
            db.close()

    def _start_sex_detection(self) -> None:
        if self._sex_detection_worker is not None and self._sex_detection_worker.isRunning():
            return

        answer = QMessageBox.question(
            self,
            "Détection du sexe",
            (
                "Lancer la détection automatique du sexe à partir du prénom "
                "pour les contacts sans sexe renseigné ?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        worker = ContactSexDetectionWorker(self)
        worker.finished.connect(self._on_sex_detection_finished)
        worker.finished.connect(worker.deleteLater)
        self._sex_detection_worker = worker
        self._detect_sex_button.setEnabled(False)
        self._status_label.setText("Détection des sexes en cours...")
        worker.start()

    def _on_sex_detection_finished(self, payload_obj: object, error: str) -> None:
        self._detect_sex_button.setEnabled(True)
        self._sex_detection_worker = None

        if error:
            QMessageBox.warning(self, "Détection du sexe", f"Échec de la détection:\n{error}")
            self._status_label.setText("Détection du sexe échouée.")
            return

        payload = dict(payload_obj)
        updated = int(payload.get("updated_contacts", 0))
        unchanged = int(payload.get("unchanged_contacts", 0))
        homme = int(payload.get("homme_count", 0))
        femme = int(payload.get("femme_count", 0))
        ambigu = int(payload.get("ambigu_count", 0))

        self._status_label.setText(f"Détection terminée: {updated} contact(s) mis à jour.")
        QMessageBox.information(
            self,
            "Détection du sexe",
            (
                f"Contacts mis à jour: {updated}\n"
                f"Inchangés: {unchanged}\n"
                f"Homme: {homme}\n"
                f"Femme: {femme}\n"
                f"Ambigu: {ambigu}"
            ),
        )
        self._reload_first_page()

    def _open_contact_detail(self, row_index: int, column_index: int) -> None:
        if column_index in {0, 1}:
            return
        if row_index < 0 or row_index >= len(self._rows):
            return

        contact_id = self._rows[row_index]["id"]
        db = SessionLocal()
        try:
            contact = contact_repository.get_by_id(db, contact_id)
        finally:
            db.close()

        if contact is None:
            QMessageBox.warning(self, "Contact introuvable", "Ce contact n'existe plus.")
            self._load_page()
            return

        dialog = ManualContactDialog(self, contact=contact)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._update_contact(dialog.payload())

    def _update_contact(self, payload: ManualContactPayload) -> None:
        if payload.contact_id is None:
            return
        fields = {
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "company_name": payload.company_name,
            "job_title": payload.job_title,
            "sex": payload.sex,
            "country": payload.country,
            "city": payload.city,
            "phone": payload.phone,
            "linkedin_url": payload.linkedin_url,
            "notes": payload.notes,
        }
        worker = ContactUpdateWorker(payload.contact_id, fields, self)
        worker.finished.connect(self._on_contact_updated)
        worker.finished.connect(worker.deleteLater)
        self._status_label.setText("Mise à jour en cours…")
        worker.start()

    def _on_contact_updated(self, result: dict, error: str) -> None:
        if error:
            QMessageBox.warning(self, "Modifier le contact", f"Impossible de mettre à jour :\n{error}")
            self._status_label.setText("Erreur lors de la mise à jour.")
            return
        self._status_label.setText("Contact mis à jour.")
        self._reload_first_page()

    def _block_selected_contact(self) -> None:
        selected_row_indices = sorted({idx.row() for idx in self._table.selectionModel().selectedRows()})
        selected_row_indices = [i for i in selected_row_indices if 0 <= i < len(self._rows)]

        if not selected_row_indices:
            QMessageBox.warning(self, "Bloquer / Débloquer", "Sélectionne d'abord au moins un contact dans la table.")
            return

        all_blocked = all(bool(self._rows[i].get("is_blocked", False)) for i in selected_row_indices)

        if all_blocked:
            # Tous bloqués → débloquer
            contact_ids = [int(self._rows[i]["id"]) for i in selected_row_indices]
            answer = QMessageBox.question(
                self,
                "Débloquer",
                f"Débloquer {len(contact_ids)} contact(s) ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            target_blocked = False
            verb = "débloqué"
        else:
            # Au moins un non-bloqué → bloquer les non-bloqués
            contact_ids = [
                int(self._rows[i]["id"])
                for i in selected_row_indices
                if not bool(self._rows[i].get("is_blocked", False))
            ]
            answer = QMessageBox.question(
                self,
                "Bloquer",
                f"Bloquer {len(contact_ids)} contact(s) ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            target_blocked = True
            verb = "bloqué"

        db = SessionLocal()
        updated_count = 0
        try:
            for contact_id in contact_ids:
                contact = contact_repository.set_blocked(db, contact_id=contact_id, is_blocked=target_blocked)
                if contact is not None:
                    updated_count += 1
            db.commit()
        except Exception as exc:
            db.rollback()
            QMessageBox.warning(self, "Bloquer / Débloquer", f"Erreur :\n{exc}")
            return
        finally:
            db.close()

        self._status_label.setText(f"{updated_count} contact(s) {verb}(s).")
        self._reload_first_page()


def _contact_to_row(contact: Any) -> dict[str, Any]:
    company = getattr(contact, "company", None)
    return {
        "id": contact.id,
        "first_name": _to_text(contact.first_name, fallback=""),
        "last_name": _to_text(contact.last_name, fallback=""),
        "sex": _to_text(getattr(contact, "sex", None), fallback=""),
        "company_name": _to_text(company.name if company else None),
        "job_title": _to_text(contact.job_title),
        "email": _to_text(contact.email),
        "country": _to_text(contact.country),
        "email_status": _to_text(contact.email_status),
        "has_been_contacted": bool(getattr(contact, "has_been_contacted", False)),
        "is_blocked": bool(contact.is_blocked),
        "notes": contact.notes or "",
    }


def _to_text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback
