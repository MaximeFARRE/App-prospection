from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
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
from services.settings_service import (
    get_collaborative_config,
    get_settings,
    get_supabase_credentials,
    load_credentials,
    save_collaborative_config,
    save_credentials,
    save_settings,
    save_supabase_credentials,
    set_collaborative_enabled,
)
from widgets.settings_widgets import AccountCard, SendLimitsSection, SyncSection
from workers.collaborative_workers import BulkContributeWorker, SupabaseLoginWorker, SupabaseSignUpWorker
from workers.settings_workers import GmailConnectionWorker, GmailSyncWorker


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SPINNER_GIF = _PROJECT_ROOT / "apps" / "desktop" / "assets" / "spinner.gif"


class SettingsView(QWidget):
    collaborative_toggled = pyqtSignal(bool)  # émis quand le toggle change

    def __init__(self) -> None:
        super().__init__()
        self._tested_accounts: dict[int, bool | None] = {}
        self._test_workers: dict[int, GmailConnectionWorker] = {}
        self._sync_worker: GmailSyncWorker | None = None
        self._login_worker: SupabaseLoginWorker | None = None
        self._signup_worker: SupabaseSignUpWorker | None = None
        self._bulk_worker: BulkContributeWorker | None = None
        self._sync_logs: list[str] = []
        self._loading_limits = False

        self._build_ui()
        self._load_persisted_settings()
        self._refresh_account_cards()
        self._auto_test_configured_accounts()

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
        self._sender_website_input = QLineEdit()
        self._sender_website_input.setPlaceholderText("https://votresite.com")
        sender_layout.addRow("Site web", self._sender_website_input)
        sender_save_btn = QPushButton("Enregistrer")
        sender_save_btn.clicked.connect(self._save_sender_credentials)
        sender_layout.addWidget(sender_save_btn)
        content.addWidget(sender_group)

        content.addWidget(self._build_collaborative_section())
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
        self._sender_website_input.setText(creds.get("sender_website", ""))

    def _refresh_account_cards(self) -> None:
        for account_index, card in self._account_cards.items():
            card.set_account(self._get_account(account_index))
            card.set_connection_ok(self._tested_accounts.get(account_index))

    def _get_account(self, account_index: int) -> GmailAccount:
        return settings.gmail_account(account_index)

    def _auto_test_configured_accounts(self) -> None:
        for account_index in (1, 2, 3):
            account = self._get_account(account_index)
            if not account.is_configured:
                continue
            self._account_cards[account_index].set_testing(True)
            worker = GmailConnectionWorker(account_index, account, self)
            worker.finished.connect(self._on_auto_test_finished)
            worker.finished.connect(worker.deleteLater)
            self._test_workers[account_index] = worker
            worker.start()

    def _on_auto_test_finished(self, payload_obj: object) -> None:
        payload = dict(payload_obj)
        account_index = int(payload["index"])
        self._test_workers.pop(account_index, None)
        self._account_cards[account_index].set_testing(False)
        self._tested_accounts[account_index] = bool(payload.get("ok"))
        self._refresh_account_cards()

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
        website = self._sender_website_input.text().strip()
        save_credentials({"sender_name": name, "sender_website": website})
        settings.sender_name = name
        settings.sender_website = website
        QMessageBox.information(self, "Expéditeur", "Informations expéditeur enregistrées.")

    # ── Section collaborative ─────────────────────────────────────────────────

    def _build_collaborative_section(self) -> QGroupBox:
        group = QGroupBox("Base collaborative (optionnel)")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        cfg = get_collaborative_config()
        supa_creds = get_supabase_credentials()

        # Toggle
        self._collab_toggle = QCheckBox("Activer le mode collaboratif")
        self._collab_toggle.setChecked(bool(cfg.get("enabled", False)))
        self._collab_toggle.toggled.connect(self._on_collab_toggled)
        layout.addWidget(self._collab_toggle)

        # ── Connexion à la base ───────────────────────────────────────────────
        db_group = QGroupBox("Connexion à la base Supabase")
        db_form = QFormLayout(db_group)
        db_form.setContentsMargins(10, 10, 10, 10)
        db_form.setSpacing(6)

        self._supabase_url_input = QLineEdit()
        self._supabase_url_input.setPlaceholderText("https://xxxxxxxxxxxx.supabase.co")
        self._supabase_url_input.setText(supa_creds.get("supabase_url", ""))
        db_form.addRow("URL de la base", self._supabase_url_input)

        self._supabase_key_input = QLineEdit()
        self._supabase_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._supabase_key_input.setPlaceholderText("eyJhbGciOiJIUzI1NiIsInR5c…  (clé anonyme)")
        self._supabase_key_input.setText(supa_creds.get("supabase_anon_key", ""))
        db_form.addRow("Clé anonyme (anon key)", self._supabase_key_input)

        save_db_btn = QPushButton("Enregistrer la connexion")
        save_db_btn.clicked.connect(self._save_supabase_credentials)
        db_form.addWidget(save_db_btn)
        layout.addWidget(db_group)

        # ── Compte utilisateur ────────────────────────────────────────────────
        user_group = QGroupBox("Compte utilisateur")
        user_form = QFormLayout(user_group)
        user_form.setContentsMargins(10, 10, 10, 10)
        user_form.setSpacing(6)

        self._collab_email = QLineEdit()
        self._collab_email.setPlaceholderText("email@exemple.com")
        self._collab_email.setText(cfg.get("user_email") or "")
        user_form.addRow("Email", self._collab_email)

        self._collab_password = QLineEdit()
        self._collab_password.setEchoMode(QLineEdit.EchoMode.Password)
        self._collab_password.setPlaceholderText("••••••••")
        user_form.addRow("Mot de passe", self._collab_password)

        login_row = QHBoxLayout()
        self._collab_login_btn = QPushButton("Connexion")
        self._collab_login_btn.clicked.connect(self._start_collab_login)
        login_row.addWidget(self._collab_login_btn)

        self._collab_signup_btn = QPushButton("Créer un compte")
        self._collab_signup_btn.clicked.connect(self._start_collab_signup)
        login_row.addWidget(self._collab_signup_btn)
        login_row.addStretch()
        user_form.addRow(login_row)
        layout.addWidget(user_group)

        # Statut
        self._collab_status_label = QLabel()
        self._collab_status_label.setWordWrap(True)
        self._refresh_collab_status(cfg)
        layout.addWidget(self._collab_status_label)

        return group

    def _refresh_collab_status(self, cfg: dict | None = None) -> None:
        if cfg is None:
            cfg = get_collaborative_config()
        user_id = cfg.get("user_id")
        credits_ = cfg.get("credits", 0)
        if user_id:
            email = cfg.get("user_email") or user_id
            self._collab_status_label.setText(
                f"● Connecté — {email} — {credits_} crédits disponibles"
            )
            self._collab_status_label.setStyleSheet("color: #16a34a;")
        else:
            self._collab_status_label.setText("Non connecté")
            self._collab_status_label.setStyleSheet("color: #64748b;")

    def _on_collab_toggled(self, enabled: bool) -> None:
        set_collaborative_enabled(enabled)
        self.collaborative_toggled.emit(enabled)

    def _save_supabase_credentials(self) -> None:
        url = self._supabase_url_input.text().strip()
        key = self._supabase_key_input.text().strip()
        if not url or not key:
            QMessageBox.warning(self, "Champs requis", "L'URL et la clé anonyme sont obligatoires.")
            return
        save_supabase_credentials(url, key)
        QMessageBox.information(self, "Supabase", "Connexion à la base enregistrée.")

    def _start_collab_login(self) -> None:
        if self._login_worker and self._login_worker.isRunning():
            return
        email = self._collab_email.text().strip()
        password = self._collab_password.text()
        if not email or not password:
            QMessageBox.warning(self, "Connexion", "Email et mot de passe requis.")
            return
        self._collab_login_btn.setEnabled(False)
        self._collab_status_label.setText("Connexion en cours…")
        self._collab_status_label.setStyleSheet("color: #64748b;")
        worker = SupabaseLoginWorker(email, password, self)
        worker.login_success.connect(self._on_login_success)
        worker.login_failed.connect(self._on_login_failed)
        worker.login_success.connect(worker.deleteLater)
        worker.login_failed.connect(worker.deleteLater)
        self._login_worker = worker
        worker.start()

    def _on_login_success(self, user_id: str, user_email: str) -> None:
        self._login_worker = None
        self._collab_login_btn.setEnabled(True)
        save_collaborative_config({"user_id": user_id, "user_email": user_email, "credits": 0})
        self._refresh_collab_status()
        QMessageBox.information(self, "Base collaborative", f"Connecté en tant que {user_email}")
        self._start_bulk_contribute(user_id)

    def _on_login_failed(self, message: str) -> None:
        self._login_worker = None
        self._collab_login_btn.setEnabled(True)
        self._collab_status_label.setText(f"Échec : {message}")
        self._collab_status_label.setStyleSheet("color: #dc2626;")

    def _start_collab_signup(self) -> None:
        if self._signup_worker and self._signup_worker.isRunning():
            return
        email = self._collab_email.text().strip()
        password = self._collab_password.text()
        if not email or not password:
            QMessageBox.warning(self, "Créer un compte", "Email et mot de passe requis.")
            return
        self._collab_signup_btn.setEnabled(False)
        self._collab_status_label.setText("Création du compte en cours…")
        self._collab_status_label.setStyleSheet("color: #64748b;")
        worker = SupabaseSignUpWorker(email, password, self)
        worker.signup_success.connect(self._on_signup_success)
        worker.signup_failed.connect(self._on_signup_failed)
        worker.signup_success.connect(worker.deleteLater)
        worker.signup_failed.connect(worker.deleteLater)
        self._signup_worker = worker
        worker.start()

    def _on_signup_success(self, user_id: str, user_email: str) -> None:
        self._signup_worker = None
        self._collab_signup_btn.setEnabled(True)
        save_collaborative_config({"user_id": user_id, "user_email": user_email, "credits": 0})
        self._refresh_collab_status()
        QMessageBox.information(
            self,
            "Base collaborative",
            f"Compte créé et connecté en tant que {user_email}.\n"
            "Vous pouvez maintenant utiliser la base collaborative.",
        )
        self._start_bulk_contribute(user_id)

    def _on_signup_failed(self, message: str) -> None:
        self._signup_worker = None
        self._collab_signup_btn.setEnabled(True)
        self._collab_status_label.setText(f"Échec : {message}")
        self._collab_status_label.setStyleSheet("color: #dc2626;")

    def _start_bulk_contribute(self, user_id: str) -> None:
        if self._bulk_worker and self._bulk_worker.isRunning():
            return
        worker = BulkContributeWorker(user_id, self)
        worker.finished.connect(self._on_bulk_contribute_done)
        worker.finished.connect(worker.deleteLater)
        worker.error.connect(worker.deleteLater)
        self._bulk_worker = worker
        worker.start()

    def _on_bulk_contribute_done(self, contributed: int, skipped: int) -> None:
        self._bulk_worker = None
        if contributed:
            self._collab_status_label.setText(
                f"● Connecté — {contributed} contact(s) partagés avec la base collaborative"
            )

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
