from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.db.session import SessionLocal
from app.repositories import contact_repository


class _DashboardStatsLoader(QThread):
    loaded = pyqtSignal(int, object, str)

    def __init__(self, request_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._request_id = request_id

    def run(self) -> None:
        db = SessionLocal()
        try:
            stats = contact_repository.get_stats(db)
            self.loaded.emit(self._request_id, stats, "")
        except Exception as exc:  # pragma: no cover - sécurité UI
            self.loaded.emit(self._request_id, {}, str(exc))
        finally:
            db.close()


class _StatCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(self._title_label)

        self._value_label = QLabel("-")
        self._value_label.setStyleSheet("color: #0f172a; font-size: 28px; font-weight: 700;")
        self._value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._value_label)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)


class DashboardView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._request_id = 0
        self._active_loader: _DashboardStatsLoader | None = None
        self._cards: dict[str, _StatCard] = {}

        self._build_ui()
        self._load_stats()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("Dashboard")
        title.setStyleSheet("color: #0f172a; font-size: 24px; font-weight: 700;")
        header_row.addWidget(title)
        header_row.addStretch(1)

        self._refresh_button = QPushButton("Actualiser")
        self._refresh_button.clicked.connect(self._load_stats)
        header_row.addWidget(self._refresh_button)
        root.addLayout(header_row)

        self._status_label = QLabel("Chargement des statistiques...")
        self._status_label.setStyleSheet("color: #64748b; font-size: 12px;")
        root.addWidget(self._status_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        card_definitions = [
            ("contacts_total", "Nombre de contacts"),
            ("companies_total", "Nombre d'entreprises"),
            ("emails_sent_total", "Emails envoyés"),
            ("replies_total", "Réponses reçues"),
            ("reply_rate_percent", "Taux de réponse"),
            ("contacts_blocked", "Contacts bloqués"),
        ]

        for index, (key, label) in enumerate(card_definitions):
            row = index // 3
            column = index % 3
            card = _StatCard(label, self)
            self._cards[key] = card
            grid.addWidget(card, row, column)

        root.addLayout(grid)
        root.addStretch(1)

    def _load_stats(self) -> None:
        self._set_loading_state(True)
        self._request_id += 1

        loader = _DashboardStatsLoader(self._request_id, self)
        loader.loaded.connect(self._on_stats_loaded)
        loader.finished.connect(loader.deleteLater)
        self._active_loader = loader
        loader.start()

    def _on_stats_loaded(self, request_id: int, stats_obj: object, error: str) -> None:
        if request_id != self._request_id:
            return

        self._set_loading_state(False)

        if error:
            self._status_label.setText("Erreur lors du chargement des statistiques.")
            return

        stats = dict(stats_obj)
        self._cards["contacts_total"].set_value(_format_int(stats.get("contacts_total")))
        self._cards["companies_total"].set_value(_format_int(stats.get("companies_total")))
        self._cards["emails_sent_total"].set_value(_format_int(stats.get("emails_sent_total")))
        self._cards["replies_total"].set_value(_format_int(stats.get("replies_total")))
        self._cards["reply_rate_percent"].set_value(_format_percent(stats.get("reply_rate_percent")))
        self._cards["contacts_blocked"].set_value(_format_int(stats.get("contacts_blocked")))

        self._status_label.setText("Statistiques à jour.")

    def _set_loading_state(self, loading: bool) -> None:
        self._refresh_button.setEnabled(not loading)
        if loading:
            self._status_label.setText("Chargement des statistiques...")


def _format_int(value: Any) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "0"
    return f"{number:,}".replace(",", " ")


def _format_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0.00 %"
    return f"{number:.2f} %"

