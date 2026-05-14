"""Scoring qualité d'un contact avant contribution à la base collaborative."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.models.contact import Contact
from app.utils.email_normalization import is_valid_email, normalize_email


_CONSUMER_DOMAINS: frozenset[str] = frozenset({
    "gmail.com", "hotmail.com", "hotmail.fr", "yahoo.com", "yahoo.fr",
    "outlook.com", "live.com", "free.fr", "orange.fr", "wanadoo.fr",
    "laposte.net", "sfr.fr", "icloud.com", "msn.com", "bbox.fr",
    "numericable.fr", "noos.fr", "voila.fr",
})

_LINKEDIN_PREFIXES: tuple[str, ...] = (
    "https://www.linkedin.com/in/",
    "https://linkedin.com/in/",
    "http://www.linkedin.com/in/",
    "http://linkedin.com/in/",
)

# Points par critère (total max = 100)
_SCORE_EMAIL_FORMAT    = 25
_SCORE_EMAIL_VERIFIED  = 20
_SCORE_PRO_DOMAIN      = 15
_SCORE_FULL_NAME       = 15
_SCORE_COMPANY         = 15
_SCORE_LINKEDIN        = 10


@dataclass
class ValidationResult:
    is_valid: bool
    score: int
    rejection_reason: Optional[str]


class ContactValidationService:
    def __init__(self, threshold: int = 60) -> None:
        self._threshold = threshold

    # ── API publique ──────────────────────────────────────────────────────────

    def score(self, contact: Contact) -> int:
        """Retourne un score qualité 0–100."""
        total = 0

        email_ok = is_valid_email(contact.email)
        if email_ok:
            total += _SCORE_EMAIL_FORMAT

            if contact.email_status == "valid":
                total += _SCORE_EMAIL_VERIFIED

            if self._is_professional_domain(contact.email):
                total += _SCORE_PRO_DOMAIN

        if contact.first_name and contact.last_name:
            total += _SCORE_FULL_NAME

        if contact.company_id is not None:
            total += _SCORE_COMPANY

        if self._has_valid_linkedin(contact.linkedin_url):
            total += _SCORE_LINKEDIN

        return total

    def validate(self, contact: Contact) -> ValidationResult:
        """Retourne (is_valid, score, rejection_reason)."""
        s = self.score(contact)

        if not contact.email:
            return ValidationResult(
                is_valid=False,
                score=s,
                rejection_reason="Email manquant",
            )
        if not is_valid_email(contact.email):
            return ValidationResult(
                is_valid=False,
                score=s,
                rejection_reason="Format d'email invalide",
            )
        if s < self._threshold:
            return ValidationResult(
                is_valid=False,
                score=s,
                rejection_reason=(
                    f"Score insuffisant ({s}/{self._threshold} requis)"
                ),
            )
        return ValidationResult(is_valid=True, score=s, rejection_reason=None)

    # ── Helpers privés ────────────────────────────────────────────────────────

    def _is_professional_domain(self, email: str) -> bool:
        """Retourne True si le domaine n'est pas un fournisseur grand public."""
        normalized = normalize_email(email)
        if not normalized or "@" not in normalized:
            return False
        domain = normalized.split("@", 1)[1]
        return domain not in _CONSUMER_DOMAINS

    def _has_valid_linkedin(self, url: Optional[str]) -> bool:
        """Retourne True si l'URL ressemble à un profil LinkedIn valide."""
        if not url:
            return False
        stripped = url.strip()
        return any(stripped.startswith(prefix) for prefix in _LINKEDIN_PREFIXES)
