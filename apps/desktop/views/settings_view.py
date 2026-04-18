from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.config import GmailAccount, settings
from services.gmail_setup_service import launch_gmail_setup
from services.settings_service import get_settings, save_settings
from widgets.settings_widgets import AccountCard, SendLimitsSection, SyncSection
from workers.settings_workers import GmailConnectionWorker, GmailSyncWorker


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SPINNER_GIF = _PROJECT_ROOT / "apps" / "desktop" / "assets" / "spinner.gif"


class SettingsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._tested_accounts: dict[int, bool | None] = {}
        self._test_workers: dict[int, GmailConnectionWorker] = {}
        self._sync_worker: GmailSyncWorker | None = None
        self._sync_logs: list[str] = []
        self._loading_limits = False

        self._build_ui()
        self._load_persisted_settings()
        self._refresh_account_cards()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        content = QVBoxLayout(container)
        content.setContentsMargins(16, 16, 16, 16)
        content.setSpacing(12)

        title = QLabel("Paramètres")
        title.setStyleSheet("color: #0f172a; font-size: 24px; font-weight: 700;")
        content.addWidget(title)

        accounts_group = QGroupBox("Comptes Gmail")
        accounts_layout = QVBoxLayout(accounts_group)
        accounts_layout.setContentsMargins(12, 12, 12, 12)
        accounts_layout.setSpacing(10)

        self._account_cards: dict[int, AccountCard] = {}
        for account_index in (1, 2):
            card = AccountCard(account_index, self)
            card.test_requested.connect(self._test_account_connection)
            card.reconfigure_requested.connect(self._open_reconfigure_dialog)
            self._account_cards[account_index] = card
            accounts_layout.addWidget(card)
        content.addWidget(accounts_group)

        self._sync_section = SyncSection(str(_SPINNER_GIF), self)
        self._sync_section.sync_button.clicked.connect(self._start_sync)
        content.addWidget(self._sync_section)

        self._send_limits_section = SendLimitsSection(self)
        self._send_limits_section.daily_limit_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.min_delay_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.max_delay_spin.valueChanged.connect(self._on_send_limits_changed)
        content.addWidget(self._send_limits_section)
        content.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _load_persisted_settings(self) -> None:
        persisted = get_settings()
        limits = self._send_limits_section

        self._loading_limits = True
        limits.daily_limit_spin.setValue(int(persisted["daily_send_limit_per_account"]))
        limits.min_delay_spin.setValue(int(persisted["min_delay_between_sends_sec"]))
        limits.max_delay_spin.setValue(int(persisted["max_delay_between_sends_sec"]))
        limits.max_delay_spin.setMinimum(limits.min_delay_spin.value() + 1)
        self._loading_limits = False

        self._refresh_last_sync_label(persisted.get("last_gmail_sync_at"))

    def _refresh_account_cards(self) -> None:
        for account_index, card in self._account_cards.items():
            card.set_account(self._get_account(account_index))
            card.set_connection_ok(self._tested_accounts.get(account_index))

    def _get_account(self, account_index: int) -> GmailAccount:
        if account_index == 1:
            return settings.gmail_account_1
        return settings.gmail_account_2

    def _test_account_connection(self, account_index: int) -> None:
        account = self._get_account(account_index)
        if not account.is_configured:
            QMessageBox.warning(self, "Compte non configuré", "Configure d'abord ce compte Gmail.")
            return

        self._account_cards[account_index].set_testing(True)
        worker = GmailConnectionWorker(account_index, account, self)
        worker.finished.connect(self._on_account_test_finished)
        worker.finished.connect(worker.deleteLater)
        self._test_workers[account_index] = worker
        worker.start()

    def _on_account_test_finished(self, payload_obj: object) -> None:
        payload = dict(payload_obj)
        account_index = int(payload["index"])
        self._test_workers.pop(account_index, None)
        self._account_cards[account_index].set_testing(False)

        if payload.get("ok"):
            self._tested_accounts[account_index] = True
            self._refresh_account_cards()
            profile = dict(payload.get("profile", {}))
            QMessageBox.information(
                self,
                "Connexion Gmail",
                "Connexion OK\n\n"
                f"Email: {profile.get('emailAddress', '-')}\n"
                f"Messages: {profile.get('messagesTotal', '-')}\n"
                f"Threads: {profile.get('threadsTotal', '-')}",
            )
            return

        self._tested_accounts[account_index] = False
        self._refresh_account_cards()
        QMessageBox.warning(self, "Connexion Gmail", f"Échec du test:\n{payload.get('error', 'Erreur inconnue')}")

    def _open_reconfigure_dialog(self, account_index: int) -> None:
        account = self._get_account(account_index)
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Reconfigurer le compte Gmail {account_index}")
        form = QFormLayout(dialog)

        client_id_input = QLineEdit(account.client_id)
        client_secret_input = QLineEdit(account.client_secret)
        client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        label_input = QLineEdit(str(account_index))
        form.addRow("Client ID", client_id_input)
        form.addRow("Client Secret", client_secret_input)
        form.addRow("Account label", label_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Lancer la configuration")
        form.addWidget(buttons)

        def _submit() -> None:
            if not client_id_input.text().strip() or not client_secret_input.text().strip():
                QMessageBox.warning(dialog, "Champs obligatoires", "Client ID et Client Secret sont requis.")
                return
            dialog.accept()

        buttons.accepted.connect(_submit)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        client_id = client_id_input.text().strip()
        client_secret = client_secret_input.text().strip()
        account_label = label_input.text().strip() or str(account_index)

        setattr(settings, f"gmail_client_id_{account_index}", client_id)
        setattr(settings, f"gmail_client_secret_{account_index}", client_secret)
        self._tested_accounts.pop(account_index, None)
        self._refresh_account_cards()

        try:
            launch_gmail_setup(client_id, client_secret, account_label)
        except OSError as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible de lancer gmail_setup.py:\n{exc}")
            return

        QMessageBox.information(
            self,
            "Configuration Gmail",
            "Le script gmail_setup.py a été lancé dans un terminal.\n"
            "Termine l'auth Google, puis copie le refresh token affiché.",
        )

    def _start_sync(self) -> None:
        if self._sync_worker is not None and self._sync_worker.isRunning():
            return

        self._sync_logs.clear()
        self._sync_section.sync_log_label.setText("")
        self._sync_section.sync_button.setEnabled(False)
        self._sync_section.set_busy(True)

        worker = GmailSyncWorker(self._sync_section.sync_days_spin.value(), self)
        worker.progress.connect(self._append_sync_log)
        worker.error.connect(self._on_sync_error)
        worker.finished.connect(self._on_sync_finished)
        worker.error.connect(worker.deleteLater)
        worker.finished.connect(worker.deleteLater)
        self._sync_worker = worker
        worker.start()

    def _append_sync_log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {message}"
        self._sync_logs.append(line)
        self._sync_section.sync_log_label.setText("\n".join(self._sync_logs))

    def _on_sync_finished(self, payload_obj: object) -> None:
        payload = dict(payload_obj)
        self._sync_worker = None
        self._sync_section.sync_button.setEnabled(True)
        self._sync_section.set_busy(False)

        finished_at = datetime.now().isoformat(timespec="seconds")
        save_settings({"last_gmail_sync_at": finished_at})
        self._refresh_last_sync_label(finished_at)

        new_entries = int(payload.get("new_entries", 0))
        matched = int(payload.get("matched", 0))
        self._append_sync_log(f"{new_entries} nouveaux contacts marqués contactés ({matched} matched)")

        errors = list(payload.get("errors", []))
        if errors:
            self._append_sync_log(f"⚠ {len(errors)} erreurs pendant la sync")

    def _on_sync_error(self, message: str) -> None:
        self._sync_worker = None
        self._sync_section.sync_button.setEnabled(True)
        self._sync_section.set_busy(False)
        self._append_sync_log(f"Erreur de synchronisation : {message}")
        QMessageBox.critical(self, "Synchronisation Gmail", message)

    def _refresh_last_sync_label(self, raw_value: Any) -> None:
        if not raw_value:
            self._sync_section.last_sync_label.setText("Dernière sync : jamais")
            return
        try:
            parsed = datetime.fromisoformat(str(raw_value))
            formatted = parsed.strftime("%d/%m/%Y %H:%M:%S")
        except ValueError:
            formatted = str(raw_value)
        self._sync_section.last_sync_label.setText(f"Dernière sync : {formatted}")

    def _on_send_limits_changed(self) -> None:
        if self._loading_limits:
            return

        limits = self._send_limits_section
        minimum = limits.min_delay_spin.value()
        limits.max_delay_spin.setMinimum(minimum + 1)
        if limits.max_delay_spin.value() <= minimum:
            limits.max_delay_spin.setValue(minimum + 1)

        settings.daily_send_limit_per_account = limits.daily_limit_spin.value()
        settings.min_delay_between_sends_sec = limits.min_delay_spin.value()
        settings.max_delay_between_sends_sec = limits.max_delay_spin.value()

        save_settings(
            {
                "daily_send_limit_per_account": settings.daily_send_limit_per_account,
                "min_delay_between_sends_sec": settings.min_delay_between_sends_sec,
                "max_delay_between_sends_sec": settings.max_delay_between_sends_sec,
            }
        )
