from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QMovie
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import GmailAccount


class AccountCard(QFrame):
    test_requested = pyqtSignal(int)
    reconfigure_requested = pyqtSignal(int)

    def __init__(self, account_index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._account_index = account_index
        self._account: GmailAccount | None = None
        self._connection_ok: bool | None = None

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._email_label = QLabel()
        self._email_label.setStyleSheet("color: #0f172a; font-size: 14px; font-weight: 600;")
        layout.addWidget(self._email_label)

        self._status_label = QLabel()
        self._status_label.setStyleSheet("color: #475569; font-size: 12px;")
        layout.addWidget(self._status_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._test_button = QPushButton("Tester la connexion")
        self._test_button.clicked.connect(lambda: self.test_requested.emit(self._account_index))
        actions.addWidget(self._test_button)

        reconfigure_button = QPushButton("Reconfigurer")
        reconfigure_button.clicked.connect(lambda: self.reconfigure_requested.emit(self._account_index))
        actions.addWidget(reconfigure_button)

        actions.addStretch(1)
        layout.addLayout(actions)

    def set_account(self, account: GmailAccount) -> None:
        self._account = account
        self._email_label.setText(account.email or f"Compte {self._account_index}")
        self._refresh_status()

    def set_connection_ok(self, value: bool | None) -> None:
        self._connection_ok = value
        self._refresh_status()

    def set_testing(self, testing: bool) -> None:
        self._test_button.setEnabled(not testing)
        if testing:
            self._test_button.setText("Test en cours...")
        else:
            self._test_button.setText("Tester la connexion")

    def _refresh_status(self) -> None:
        if self._connection_ok is True:
            self._status_label.setText("🟢 Connexion OK")
            return

        if self._account and self._account.refresh_token:
            self._status_label.setText("🟡 Token présent")
            return

        self._status_label.setText("🔴 Non configuré")


class SyncSection(QGroupBox):
    def __init__(self, spinner_gif_path: str, parent: QWidget | None = None) -> None:
        super().__init__("Synchronisation", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.last_sync_label = QLabel("Dernière sync : jamais")
        self.last_sync_label.setStyleSheet("color: #334155; font-size: 12px;")
        layout.addWidget(self.last_sync_label)

        days_row = QHBoxLayout()
        days_label = QLabel("Limiter aux N derniers jours (0 = tout)")
        self.sync_days_spin = QSpinBox()
        self.sync_days_spin.setRange(0, 3650)
        self.sync_days_spin.setValue(0)
        days_row.addWidget(days_label)
        days_row.addStretch(1)
        days_row.addWidget(self.sync_days_spin)
        layout.addLayout(days_row)

        self.sync_button = QPushButton("Synchroniser maintenant")
        layout.addWidget(self.sync_button)

        spinner_row = QHBoxLayout()
        self.spinner_icon_label = QLabel()
        self.spinner_icon_label.setFixedSize(20, 20)
        self.spinner_movie = QMovie(spinner_gif_path)
        if self.spinner_movie.isValid():
            self.spinner_movie.setScaledSize(QSize(18, 18))
            self.spinner_icon_label.setMovie(self.spinner_movie)
        else:
            self.spinner_icon_label.setText("⏳")
        self.spinner_text_label = QLabel("Synchronisation en cours...")
        spinner_row.addWidget(self.spinner_icon_label)
        spinner_row.addWidget(self.spinner_text_label)
        spinner_row.addStretch(1)
        self.spinner_icon_label.hide()
        self.spinner_text_label.hide()
        layout.addLayout(spinner_row)

        self.sync_log_label = QLabel("")
        self.sync_log_label.setWordWrap(True)
        self.sync_log_label.setStyleSheet(
            "background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; "
            "font-size: 12px; color: #334155;"
        )
        self.sync_log_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.sync_log_label)

    def set_busy(self, busy: bool) -> None:
        self.spinner_icon_label.setVisible(busy)
        self.spinner_text_label.setVisible(busy)
        if not self.spinner_movie.isValid():
            return
        if busy:
            self.spinner_movie.start()
        else:
            self.spinner_movie.stop()


class SendLimitsSection(QGroupBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Limites d'envoi", parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.daily_limit_spin = QSpinBox()
        self.daily_limit_spin.setRange(1, 1000)
        layout.addRow("Emails / jour / compte", self.daily_limit_spin)

        self.hourly_limit_spin = QSpinBox()
        self.hourly_limit_spin.setRange(1, 200)
        layout.addRow("Emails / heure / compte", self.hourly_limit_spin)

        self.min_delay_spin = QSpinBox()
        self.min_delay_spin.setRange(1, 3600)
        layout.addRow("Délai min entre envois (sec)", self.min_delay_spin)

        self.max_delay_spin = QSpinBox()
        self.max_delay_spin.setRange(2, 7200)
        layout.addRow("Délai max entre envois (sec)", self.max_delay_spin)

        self.company_weekly_limit_spin = QSpinBox()
        self.company_weekly_limit_spin.setRange(1, 100)
        layout.addRow("Max mails / entreprise / semaine", self.company_weekly_limit_spin)

        self.weight_1_spin = QSpinBox()
        self.weight_1_spin.setRange(1, 99)
        self.weight_1_spin.setSuffix(" %")
        layout.addRow("Poids compte 1 (compte 2 = reste)", self.weight_1_spin)
