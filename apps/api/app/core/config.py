from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Racine du projet = 3 niveaux au-dessus de ce fichier (core/ → app/ → api/ → Apps prospection/)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DB_URL = f"sqlite:///{(_PROJECT_ROOT / 'data' / 'app.db').as_posix()}"


class GmailAccount(BaseSettings):
    """Représente un compte Gmail configuré (client_id, secret, refresh_token, adresse)."""

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    email: str = ""

    @property
    def is_configured(self) -> bool:
        """Vrai si les 4 champs sont renseignés."""
        return all([self.client_id, self.client_secret, self.refresh_token, self.email])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Base de données ───────────────────────────────────────────────────────
    database_url: str = _DEFAULT_DB_URL

    # ─── API ───────────────────────────────────────────────────────────────────
    api_host: str = "localhost"
    api_port: int = 8000
    secret_key: str = "change-this-secret-key-before-production"

    # ─── Gmail – Compte 1 ────────────────────────────────────────────────────
    gmail_client_id_1: str = ""
    gmail_client_secret_1: str = ""
    gmail_refresh_token_1: str = ""
    gmail_email_1: str = ""

    # ─── Gmail – Compte 2 ────────────────────────────────────────────────────
    gmail_client_id_2: str = ""
    gmail_client_secret_2: str = ""
    gmail_refresh_token_2: str = ""
    gmail_email_2: str = ""

    # ─── Gmail – Compte 3 ────────────────────────────────────────────────────
    gmail_client_id_3: str = ""
    gmail_client_secret_3: str = ""
    gmail_refresh_token_3: str = ""
    gmail_email_3: str = ""

    # ─── Expéditeur ───────────────────────────────────────────────────────────
    sender_name: str = ""

    # ─── Pièce jointe CV ──────────────────────────────────────────────────────
    cv_path: str = str(_PROJECT_ROOT / "data" / "Cv_maxime_farre.pdf")

    # ─── Limites d'envoi ───────────────────────────────────────────────────────
    daily_send_limit_per_account: int = 30
    hourly_send_limit_per_account: int = 5
    min_delay_between_sends_sec: int = 60
    max_delay_between_sends_sec: int = 180

    # ─── Répartition des comptes (poids relatifs, ne doivent pas sommer à 100) ─
    # random.choices normalise automatiquement les poids.
    # Ex : [50, 30, 20] → compte 1 : 50 %, compte 2 : 30 %, compte 3 : 20 %
    gmail_weight_1: int = 50
    gmail_weight_2: int = 50
    gmail_weight_3: int = 50

    # ─── Protection anti-spam entreprise ──────────────────────────────────────
    company_weekly_send_limit: int = 4

    @field_validator("max_delay_between_sends_sec")
    @classmethod
    def max_delay_must_exceed_min(cls, v: int, info) -> int:
        minimum = info.data.get("min_delay_between_sends_sec", 0)
        if v <= minimum:
            raise ValueError(
                f"max_delay_between_sends_sec ({v}) doit être supérieur à "
                f"min_delay_between_sends_sec ({minimum})"
            )
        return v

    # ─── Helpers ───────────────────────────────────────────────────────────────

    def gmail_account(self, index: int) -> GmailAccount:
        """Retourne le GmailAccount pour le slot N (1-based)."""
        return GmailAccount(
            client_id=getattr(self, f"gmail_client_id_{index}", ""),
            client_secret=getattr(self, f"gmail_client_secret_{index}", ""),
            refresh_token=getattr(self, f"gmail_refresh_token_{index}", ""),
            email=getattr(self, f"gmail_email_{index}", ""),
        )

    # Alias pour la rétrocompatibilité avec le code existant
    @property
    def gmail_account_1(self) -> GmailAccount:
        return self.gmail_account(1)

    @property
    def gmail_account_2(self) -> GmailAccount:
        return self.gmail_account(2)

    @property
    def gmail_account_3(self) -> GmailAccount:
        return self.gmail_account(3)

    @property
    def configured_gmail_accounts(self) -> list[GmailAccount]:
        """Retourne les comptes Gmail configurés (slots 1-3, extensible)."""
        accounts = []
        for i in range(1, 4):          # slots 1, 2, 3 — ajouter 4 ici pour un 4e compte
            account = self.gmail_account(i)
            if account.is_configured:
                accounts.append(account)
        return accounts


settings = Settings()
