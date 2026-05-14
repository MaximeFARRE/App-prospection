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
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.config import GmailAccount, settings
from services.gmail_setup_service import launch_gmail_setup
from services.settings_service import get_settings, load_credentials, save_credentials, save_settings
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
        for account_index in (1, 2, 3):
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
        self._send_limits_section.hourly_limit_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.min_delay_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.max_delay_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.company_weekly_limit_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.weight_1_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.weight_2_spin.valueChanged.connect(self._on_send_limits_changed)
        self._send_limits_section.weight_3_spin.valueChanged.connect(self._on_send_limits_changed)
        content.addWidget(self._send_limits_section)

        qev_group = QGroupBox("Vérification email (QuickEmailVerification)")
        qev_layout = QFormLayout(qev_group)
        qev_layout.setContentsMargins(12, 12, 12, 12)
        qev_layout.setSpacing(8)
        self._qev_key_input = QLineEdit()
        self._qev_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._qev_key_input.setPlaceholderText("Clé API principale")
        qev_layout.addRow("Clé primaire", self._qev_key_input)
        self._qev_key_2_input = QLineEdit()
        self._qev_key_2_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._qev_key_2_input.setPlaceholderText("Clé API secondaire (optionnel)")
        qev_layout.addRow("Clé secondaire", self._qev_key_2_input)
        qev_save_btn = QPushButton("Enregistrer les clés QEV")
        qev_save_btn.clicked.connect(self._save_qev_credentials)
        qev_layout.addWidget(qev_save_btn)
        content.addWidget(qev_group)

        sender_group = QGroupBox("Expéditeur")
        sender_layout = QFormLayout(sender_group)
        sender_layout.setContentsMargins(12, 12, 12, 12)
        sender_layout.setSpacing(8)
        self._sender_name_input = QLineEdit()
        self._sender_name_input.setPlaceholderText("Prénom Nom")
        sender_layout.addRow("Nom expéditeur", self._sender_name_input)
        sender_save_btn = QPushButton("Enregistrer")
        sender_save_btn.clicked.connect(self._save_sender_credentials)
        sender_layout.addWidget(sender_save_btn)
        content.addWidget(sender_group)

        content.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _load_persisted_settings(self) -> None:
        persisted = get_settings()
        limits = self._send_limits_section

        self._loading_limits = True
        limits.daily_limit_spin.setValue(int(persisted["daily_send_limit_per_account"]))
        limits.hourly_limit_spin.setValue(int(persisted["hourly_send_limit_per_account"]))
        limits.min_delay_spin.setValue(int(persisted["min_delay_between_sends_sec"]))
        limits.max_delay_spin.setValue(int(persisted["max_delay_between_sends_sec"]))
        limits.max_delay_spin.setMinimum(limits.min_delay_spin.value() + 1)
        limits.company_weekly_limit_spin.setValue(int(persisted["company_weekly_send_limit"]))
        limits.weight_1_spin.setValue(int(persisted["gmail_weight_1"]))
        limits.weight_2_spin.setValue(int(persisted["gmail_weight_2"]))
        limits.weight_3_spin.setValue(int(persisted["gmail_weight_3"]))
        self._loading_limits = False

        self._refresh_last_sync_label(persisted.get("last_gmail_sync_at"))

        creds = load_credentials()
        self._qev_key_input.setText(creds.get("quickemailverification_api_key", ""))
        self._qev_key_2_input.setText(creds.get("quickemailverification_api_key_2", ""))
        self._sender_name_input.setText(creds.get("sender_name", ""))

    def _refresh_account_cards(self) -> None:
        for account_index, card in self._account_cards.items():
            card.set_account(self._get_account(account_index))
            card.set_connection_ok(self._tested_accounts.get(account_index))

    def _get_account(self, account_index: int) -> GmailAccount:
        return settings.gmail_account(account_index)

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
        dialog.setMinimumWidth(480)
        form = QFormLayout(dialog)
        form.setSpacing(10)

        client_id_input = QLineEdit(account.client_id)
        client_secret_input = QLineEdit(account.client_secret)
        client_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        email_input = QLineEdit(account.email)
        email_input.setPlaceholderText("votre.adresse@gmail.com")
        refresh_token_input = QLineEdit(account.refresh_token)
        refresh_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        refresh_token_input.setPlaceholderText("Colle ici le refresh_token après l'auth Google")
        label_input = QLineEdit(str(account_index))

        form.addRow("Client ID *", client_id_input)
        form.addRow("Client Secret *", client_secret_input)
        form.addRow("Adresse Gmail *", email_input)
        form.addRow("Refresh Token", refresh_token_input)
        form.addRow("Account label", label_input)

        hint = QLabel(
            "Si vous n'avez pas encore de refresh_token, laissez ce champ vide\n"
            "et cliquez sur « Lancer l'auth Google » pour en obtenir un."
        )
        hint.setStyleSheet("color: #64748b; font-size: 11px;")
        hint.setWordWrap(True)
        form.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Enregistrer")
        form.addWidget(buttons)

        auth_btn = QPushButton("Lancer l'auth Google (obtenir un refresh_token)")
        form.addWidget(auth_btn)

        def _submit() -> None:
            if not client_id_input.text().strip() or not client_secret_input.text().strip():
                QMessageBox.warning(dialog, "Champs obligatoires", "Client ID et Client Secret sont requis.")
                return
            if not email_input.text().strip():
                QMessageBox.warning(dialog, "Champs obligatoires", "L'adresse Gmail est requise.")
                return
            dialog.accept()

        def _launch_auth() -> None:
            cid = client_id_input.text().strip()
            csecret = client_secret_input.text().strip()
            if not cid or not csecret:
                QMessageBox.warning(dialog, "Champs obligatoires", "Client ID et Client Secret sont requis avant de lancer l'auth.")
                return
            alabel = label_input.text().strip() or str(account_index)
            try:
                launch_gmail_setup(cid, csecret, alabel)
            except OSError as exc:
                QMessageBox.critical(dialog, "Erreur", f"Impossible de lancer gmail_setup.py:\n{exc}")
                return
            QMessageBox.information(
                dialog,
                "Auth Google",
                "Le script gmail_setup.py a été lancé dans un terminal.\n"
                "Termine l'auth Google, puis colle le refresh_token affiché dans le champ prévu.",
            )

        buttons.accepted.connect(_submit)
        buttons.rejected.connect(dialog.reject)
        auth_btn.clicked.connect(_launch_auth)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        client_id = client_id_input.text().strip()
        client_secret = client_secret_input.text().strip()
        gmail_email = email_input.text().strip()
        refresh_token = refresh_token_input.text().strip()

        setattr(settings, f"gmail_client_id_{account_index}", client_id)
        setattr(settings, f"gmail_client_secret_{account_index}", client_secret)
        setattr(settings, f"gmail_email_{account_index}", gmail_email)
        if refresh_token:
            setattr(settings, f"gmail_refresh_token_{account_index}", refresh_token)

        creds: dict[str, str] = {
            f"gmail_client_id_{account_index}": client_id,
            f"gmail_client_secret_{account_index}": client_secret,
            f"gmail_email_{account_index}": gmail_email,
        }
        if refresh_token:
            creds[f"gmail_refresh_token_{account_index}"] = refresh_token
        save_credentials(creds)

        self._tested_accounts.pop(account_index, None)
        self._refresh_account_cards()
        QMessageBox.information(self, "Configuration Gmail", "Les informations du compte ont été enregistrées.")

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

    def _save_qev_credentials(self) -> None:
        key1 = self._qev_key_input.text().strip()
        key2 = self._qev_key_2_input.text().strip()
        save_credentials({
            "quickemailverification_api_key": key1,
            "quickemailverification_api_key_2": key2,
        })
        settings.quickemailverification_api_key = key1
        settings.quickemailverification_api_key_2 = key2
        QMessageBox.information(self, "QEV", "Clés QuickEmailVerification enregistrées.")

    def _save_sender_credentials(self) -> None:
        name = self._sender_name_input.text().strip()
        save_credentials({"sender_name": name})
        settings.sender_name = name
        QMessageBox.information(self, "Expéditeur", "Nom d'expéditeur enregistré.")

    def _on_send_limits_changed(self) -> None:
        if self._loading_limits:
            return

        limits = self._send_limits_section
        minimum = limits.min_delay_spin.value()
        limits.max_delay_spin.setMinimum(minimum + 1)
        if limits.max_delay_spin.value() <= minimum:
            limits.max_delay_spin.setValue(minimum + 1)

        settings.daily_send_limit_per_account  = limits.daily_limit_spin.value()
        settings.hourly_send_limit_per_account = limits.hourly_limit_spin.value()
        settings.min_delay_between_sends_sec   = limits.min_delay_spin.value()
        settings.max_delay_between_sends_sec   = limits.max_delay_spin.value()
        settings.company_weekly_send_limit     = limits.company_weekly_limit_spin.value()
        settings.gmail_weight_1               = limits.weight_1_spin.value()
        settings.gmail_weight_2               = limits.weight_2_spin.value()
        settings.gmail_weight_3               = limits.weight_3_spin.value()

        save_settings({
            "daily_send_limit_per_account":  settings.daily_send_limit_per_account,
            "hourly_send_limit_per_account": settings.hourly_send_limit_per_account,
            "min_delay_between_sends_sec":   settings.min_delay_between_sends_sec,
            "max_delay_between_sends_sec":   settings.max_delay_between_sends_sec,
            "company_weekly_send_limit":     settings.company_weekly_send_limit,
            "gmail_weight_1":                settings.gmail_weight_1,
            "gmail_weight_2":                settings.gmail_weight_2,
            "gmail_weight_3":                settings.gmail_weight_3,
        })
