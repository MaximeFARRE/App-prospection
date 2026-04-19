from __future__ import annotations

from datetime import datetime
from math import ceil
from typing import Any

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
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
from app.repositories import contact_repository, reply_repository
from app.services.reply_classification_service import update_reply_sentiment
from workers.replies_workers import RepliesSyncWorker


PAGE_SIZE = 100
SENTIMENT_VALUES = ("positive", "negative", "neutral", "auto", "unknown")


class _RepliesPageLoader(QThread):
    loaded = pyqtSignal(int, object, int, str)

    def __init__(self, request_id: int, filters: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request_id = request_id
        self._filters = filters

    def run(self) -> None:
        db = SessionLocal()
        try:
            total = reply_repository.count(db, self._filters)
            replies = reply_repository.get_all(db, self._filters)
            rows = [_reply_to_row(reply) for reply in replies]
            self.loaded.emit(self._request_id, rows, total, "")
        except Exception as exc:  # pragma: no cover - securite UI
            self.loaded.emit(self._request_id, [], 0, str(exc))
        finally:
            db.close()


class RepliesView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._current_page = 1
        self._total_replies = 0
        self._rows: list[dict[str, Any]] = []
        self._request_id = 0
        self._active_loader: _RepliesPageLoader | None = None
        self._sync_worker: RepliesSyncWorker | None = None
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

        actions_row = QHBoxLayout()
        actions_row.setSpacing(8)

        self._sync_button = QPushButton("Synchro Gmail")
        actions_row.addWidget(self._sync_button)

        self._refresh_button = QPushButton("Actualiser")
        actions_row.addWidget(self._refresh_button)

        self._mark_positive_button = QPushButton("Marquer positif")
        self._mark_negative_button = QPushButton("Marquer negatif")
        self._mark_neutral_button = QPushButton("Marquer neutre")
        actions_row.addWidget(self._mark_positive_button)
        actions_row.addWidget(self._mark_negative_button)
        actions_row.addWidget(self._mark_neutral_button)

        self._block_contact_button = QPushButton("Bloquer contact")
        actions_row.addWidget(self._block_contact_button)
        actions_row.addStretch(1)
        root.addLayout(actions_row)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Recherche (nom, expéditeur, sujet)")
        filters_row.addWidget(self._search_input, stretch=2)

        self._sentiment_filter = QComboBox()
        self._sentiment_filter.addItem("Sentiment: Tous", None)
        self._sentiment_filter.addItem("positive", "positive")
        self._sentiment_filter.addItem("negative", "negative")
        self._sentiment_filter.addItem("neutral", "neutral")
        self._sentiment_filter.addItem("auto", "auto")
        self._sentiment_filter.addItem("unknown", "unknown")
        filters_row.addWidget(self._sentiment_filter, stretch=1)

        root.addLayout(filters_row)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Prénom / Nom", "Email expéditeur", "Sujet", "Sentiment", "Date reçue"]
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
        self._sentiment_filter.currentIndexChanged.connect(self._schedule_reload)
        self._sync_button.clicked.connect(self._start_sync)
        self._refresh_button.clicked.connect(self._reload_first_page)
        self._mark_positive_button.clicked.connect(lambda: self._mark_selected_reply("positive"))
        self._mark_negative_button.clicked.connect(lambda: self._mark_selected_reply("negative"))
        self._mark_neutral_button.clicked.connect(lambda: self._mark_selected_reply("neutral"))
        self._block_contact_button.clicked.connect(self._block_selected_contact)
        self._prev_button.clicked.connect(self._go_prev_page)
        self._next_button.clicked.connect(self._go_next_page)

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
        total_pages = max(1, ceil(self._total_replies / PAGE_SIZE))
        if self._current_page < total_pages:
            self._current_page += 1
            self._load_page()

    def _load_page(self) -> None:
        filters = self._build_filters()
        filters["page"] = self._current_page
        filters["page_size"] = PAGE_SIZE

        self._set_loading_state(True)
        self._request_id += 1
        loader = _RepliesPageLoader(self._request_id, filters, self)
        loader.loaded.connect(self._on_page_loaded)
        loader.finished.connect(loader.deleteLater)
        self._active_loader = loader
        loader.start()

    def _on_page_loaded(self, request_id: int, rows_obj: object, total: int, error: str) -> None:
        if request_id != self._request_id:
            return

        self._set_loading_state(False)
        if error:
            self._rows = []
            self._total_replies = 0
            self._table.setRowCount(0)
            self._status_label.setText("Erreur lors du chargement des réponses.")
            QMessageBox.critical(self, "Erreur", f"Impossible de charger les réponses:\n{error}")
            self._update_pagination_controls()
            return

        self._rows = list(rows_obj)
        self._total_replies = total

        total_pages = max(1, ceil(self._total_replies / PAGE_SIZE))
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
            self._table.setItem(row_index, 0, QTableWidgetItem(row["contact_name"]))
            self._table.setItem(row_index, 1, QTableWidgetItem(row["from_email"]))
            self._table.setItem(row_index, 2, QTableWidgetItem(row["subject"]))

            sentiment_combo = QComboBox()
            for sentiment in SENTIMENT_VALUES:
                sentiment_combo.addItem(sentiment, sentiment)
            sentiment_combo.setCurrentText(row["sentiment"])
            sentiment_combo.currentIndexChanged.connect(
                lambda _index, rid=row["reply_id"], combo=sentiment_combo: self._on_sentiment_changed(rid, combo)
            )
            self._table.setCellWidget(row_index, 3, sentiment_combo)

            self._table.setItem(row_index, 4, QTableWidgetItem(row["received_at"]))

        self._is_rendering = False
        self._status_label.setText(f"{self._total_replies} réponse(s)")

    def _update_pagination_controls(self) -> None:
        total_pages = max(1, ceil(self._total_replies / PAGE_SIZE))
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

        sentiment = self._sentiment_filter.currentData()
        if sentiment:
            filters["sentiment"] = sentiment
        return filters

    def _on_sentiment_changed(self, reply_id: int, combo: QComboBox) -> None:
        if self._is_rendering:
            return

        sentiment = str(combo.currentData() or "").strip().lower()
        row_index = self._row_index_for_reply(reply_id)
        if row_index < 0 or not sentiment:
            return

        current = self._rows[row_index]["sentiment"]
        if current == sentiment:
            return
        if not self._persist_sentiment(reply_id, sentiment):
            combo.blockSignals(True)
            combo.setCurrentText(current)
            combo.blockSignals(False)
            return
        self._rows[row_index]["sentiment"] = sentiment

    def _mark_selected_reply(self, sentiment: str) -> None:
        row_index = self._selected_row_index()
        if row_index < 0:
            QMessageBox.information(self, "Réponse", "Sélectionne d'abord une réponse.")
            return

        row = self._rows[row_index]
        if not self._persist_sentiment(row["reply_id"], sentiment):
            return
        row["sentiment"] = sentiment

        combo = self._table.cellWidget(row_index, 3)
        if isinstance(combo, QComboBox):
            combo.blockSignals(True)
            combo.setCurrentText(sentiment)
            combo.blockSignals(False)

    def _persist_sentiment(self, reply_id: int, sentiment: str) -> bool:
        db = SessionLocal()
        try:
            result = update_reply_sentiment(reply_id=reply_id, sentiment=sentiment, db=db)
            db.commit()
            self._status_label.setText(
                f"Sentiment mis à jour ({result.sentiment}) - {result.updated_campaign_states} campaign_state(s)"
            )
            return True
        except Exception as exc:
            db.rollback()
            QMessageBox.warning(self, "Mise à jour", f"Impossible de mettre à jour le sentiment:\n{exc}")
            return False
        finally:
            db.close()

    def _block_selected_contact(self) -> None:
        row_index = self._selected_row_index()
        if row_index < 0:
            QMessageBox.information(self, "Contact", "Sélectionne d'abord une réponse.")
            return

        row = self._rows[row_index]
        contact_id = row["contact_id"]
        db = SessionLocal()
        try:
            contact = contact_repository.set_blocked(db, contact_id=contact_id, is_blocked=True)
            if contact is None:
                QMessageBox.warning(self, "Contact", "Contact introuvable.")
                return
            db.commit()
            self._status_label.setText("Contact bloqué.")
        except Exception as exc:
            db.rollback()
            QMessageBox.warning(self, "Contact", f"Impossible de bloquer le contact:\n{exc}")
        finally:
            db.close()

    def _start_sync(self) -> None:
        if self._sync_worker is not None and self._sync_worker.isRunning():
            return

        self._sync_button.setEnabled(False)
        worker = RepliesSyncWorker(self)
        worker.progress.connect(self._on_sync_progress)
        worker.finished.connect(self._on_sync_finished)
        worker.finished.connect(worker.deleteLater)
        self._sync_worker = worker
        worker.start()

    def _on_sync_progress(self, message: str) -> None:
        self._status_label.setText(message)

    def _on_sync_finished(self, payload_obj: object, error: str) -> None:
        self._sync_button.setEnabled(True)
        self._sync_worker = None

        if error:
            QMessageBox.critical(self, "Synchro Gmail", f"Erreur de synchronisation:\n{error}")
            self._status_label.setText("Erreur de synchronisation Gmail.")
            return

        payload = dict(payload_obj)
        created = int(payload.get("replies_created", 0))
        updated = int(payload.get("campaign_states_updated", 0))
        self._status_label.setText(f"Synchro terminée: {created} réponse(s), {updated} state(s) mis à jour")

        errors = list(payload.get("errors", []))
        if errors:
            QMessageBox.warning(self, "Synchro Gmail", f"Synchronisation avec {len(errors)} erreur(s).")

        self._reload_first_page()

    def _selected_row_index(self) -> int:
        row_index = self._table.currentRow()
        if row_index < 0 or row_index >= len(self._rows):
            return -1
        return row_index

    def _row_index_for_reply(self, reply_id: int) -> int:
        for index, row in enumerate(self._rows):
            if row["reply_id"] == reply_id:
                return index
        return -1


def _reply_to_row(reply: Any) -> dict[str, Any]:
    contact = getattr(reply, "contact", None)
    first_name = _to_text(getattr(contact, "first_name", None), fallback="")
    last_name = _to_text(getattr(contact, "last_name", None), fallback="")
    contact_name = " ".join(part for part in [first_name, last_name] if part).strip() or "-"

    sentiment = str(getattr(reply, "sentiment", "") or "").strip().lower()
    if sentiment not in SENTIMENT_VALUES:
        sentiment = "unknown"

    return {
        "reply_id": int(reply.id),
        "contact_id": int(reply.contact_id),
        "contact_name": contact_name,
        "from_email": _to_text(reply.from_email),
        "subject": _to_text(reply.subject),
        "sentiment": sentiment,
        "received_at": _format_datetime(getattr(reply, "received_at", None)),
    }


def _to_text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return "-"
