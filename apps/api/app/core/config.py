import os
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

    # ─── Gmail – Compte 1 (secondaire) ────────────────────────────────────────
    gmail_client_id_1: str = ""
    gmail_client_secret_1: str = ""
    gmail_refresh_token_1: str = ""
    gmail_email_1: str = "maxime.farre8@gmail.com"

    # ─── Gmail – Compte 2 (principal) ─────────────────────────────────────────
    gmail_client_id_2: str = ""
    gmail_client_secret_2: str = ""
    gmail_refresh_token_2: str = ""
    gmail_email_2: str = "maxime@maxime-farre.xyz"

    # ─── Pièce jointe CV ──────────────────────────────────────────────────────
    cv_path: str = str(_PROJECT_ROOT / "data" / "Cv_maxime_farre.pdf")

    # ─── Limites d'envoi ───────────────────────────────────────────────────────
    daily_send_limit_per_account: int = 30
    hourly_send_limit_per_account: int = 5
    min_delay_between_sends_sec: int = 60
    max_delay_between_sends_sec: int = 180

    # ─── Répartition des comptes (poids en %, somme libre) ────────────────────
    # Compte 1 reçoit ce % des envois, compte 2 reçoit (100 - gmail_weight_1) %
    gmail_weight_1: int = 50

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

    @property
    def gmail_account_1(self) -> GmailAccount:
        return GmailAccount(
            client_id=self.gmail_client_id_1,
            client_secret=self.gmail_client_secret_1,
            refresh_token=self.gmail_refresh_token_1,
            email=self.gmail_email_1,
        )

    @property
    def gmail_account_2(self) -> GmailAccount:
        return GmailAccount(
            client_id=self.gmail_client_id_2,
            client_secret=self.gmail_client_secret_2,
            refresh_token=self.gmail_refresh_token_2,
            email=self.gmail_email_2,
        )

    @property
    def configured_gmail_accounts(self) -> list[GmailAccount]:
        """Retourne uniquement les comptes Gmail dont les 4 champs sont renseignés."""
        return [a for a in [self.gmail_account_1, self.gmail_account_2] if a.is_configured]


settings = Settings()
