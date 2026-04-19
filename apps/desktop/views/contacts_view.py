from __future__ import annotations

from math import ceil
from typing import Any

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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

from app.db.session import SessionLocal
from app.repositories import contact_repository
from widgets.contact_detail_dialog import ContactDetailDialog


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
        self._email_status_filter.addItem("valid", "valid")
        self._email_status_filter.addItem("invalid", "invalid")
        filters_row.addWidget(self._email_status_filter, stretch=1)

        self._blocked_filter = QComboBox()
        self._blocked_filter.addItem("Bloqué: Tous", None)
        self._blocked_filter.addItem("Oui", "blocked")
        self._blocked_filter.addItem("Non", "active")
        filters_row.addWidget(self._blocked_filter, stretch=1)

        root.addLayout(filters_row)

        self._table = QTableWidget(0, 9)
        self._table.setHorizontalHeaderLabels(
            ["Prénom", "Nom", "Sexe", "Entreprise", "Poste", "Email", "Pays", "Statut email", "Bloqué"]
        )
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
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
        self._prev_button.clicked.connect(self._go_prev_page)
        self._next_button.clicked.connect(self._go_next_page)
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
                (8, "Oui" if row["is_blocked"] else "Non"),
            ]

            for col_index, value in cells:
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row["id"])
                if col_index == 8:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
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

    def _row_index_for_contact(self, contact_id: int) -> int:
        for index, row in enumerate(self._rows):
            if row["id"] == contact_id:
                return index
        return -1

    def _open_contact_detail(self, row_index: int, _column: int) -> None:
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

        ContactDetailDialog(contact, self).exec()


def _contact_to_row(contact: Any) -> dict[str, Any]:
    company = getattr(contact, "company", None)
    return {
        "id": contact.id,
        "first_name": _to_text(contact.first_name),
        "last_name": _to_text(contact.last_name),
        "sex": _to_text(getattr(contact, "sex", None), fallback=""),
        "company_name": _to_text(company.name if company else None),
        "job_title": _to_text(contact.job_title),
        "email": _to_text(contact.email),
        "country": _to_text(contact.country),
        "email_status": _to_text(contact.email_status),
        "is_blocked": bool(contact.is_blocked),
    }


def _to_text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback
