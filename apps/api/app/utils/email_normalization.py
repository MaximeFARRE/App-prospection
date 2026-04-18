import re

# Regex minimale : local@domaine.tld
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str | None) -> str | None:
    """Normalise un email pour la déduplication.

    - Strip des espaces
    - Mise en minuscules
    - Retourne None si l'email est vide ou mal formé
    """
    if not email:
        return None
    normalized = email.strip().lower()
    if not _EMAIL_RE.match(normalized):
        return None
    return normalized


def is_valid_email(email: str | None) -> bool:
    """Vrai si l'email normalisé passe la validation basique."""
    return normalize_email(email) is not None
