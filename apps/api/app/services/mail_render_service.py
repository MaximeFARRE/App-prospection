from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import GmailAccount
from app.models.contact import Contact


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates"
_SETTINGS_PATH = _PROJECT_ROOT / "data" / "settings.json"
_ENV_PATH = _PROJECT_ROOT / ".env"

_SUPPORTED_STEPS    = frozenset({"intro", "followup_1", "followup_2"})
_SUPPORTED_LANGUAGES = frozenset({"fr", "en"})
_SUPPORTED_VARIANTS  = frozenset({"a", "b"})

# Noms de pays considérés comme France (langue française)
_FRANCE_COUNTRY_NAMES = frozenset({"france", "fr", "fra"})

_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


# ── Résultat du rendu ─────────────────────────────────────────────────────────

@dataclass(slots=True)
class RenderResult:
    subject: str
    body: str
    language: str    # "fr" ou "en"
    ab_variant: str  # "a" ou "b"


# ── API publique ──────────────────────────────────────────────────────────────

def detect_language(contact: Contact) -> str:
    """Retourne 'fr' si le contact est en France, 'en' sinon."""
    country = _as_text(getattr(contact, "country", None)).lower().strip()
    return "fr" if country in _FRANCE_COUNTRY_NAMES else "en"


def pick_ab_variant(contact_id: int) -> str:
    """Assigne le variant A/B de façon déterministe et équilibrée.

    Contacts pairs  → 'a'
    Contacts impairs → 'b'
    """
    return "a" if contact_id % 2 == 0 else "b"


def load_template(step: str, language: str, ab_variant: str) -> tuple[str, str]:
    """Charge et parse un template.  Retourne (subject_raw, body_html)."""
    _validate_step(step)
    _validate_language(language)
    _validate_variant(ab_variant)

    filename = f"{step}_{language}_{ab_variant}.md"
    template_path = _TEMPLATES_DIR / filename
    raw = template_path.read_text(encoding="utf-8")

    lines = raw.splitlines()
    if not lines:
        raise ValueError(f"Template vide : {template_path}")

    first_line = lines[0].strip()
    if not first_line.lower().startswith("subject:"):
        raise ValueError(
            f"Template invalide ({template_path}) : "
            f"première ligne attendue 'Subject: ...'"
        )

    subject = first_line.split(":", 1)[1].strip()
    body_markdown = "\n".join(lines[1:]).strip()
    body = _markdown_to_html(body_markdown)
    return subject, body


def render(
    template_subject: str,
    template_body: str,
    contact: Contact,
    account: GmailAccount,
    language: str = "fr",
) -> tuple[str, str]:
    """Remplace les variables dans un sujet et un corps déjà chargés."""
    variables = _build_variables(contact, account, language)
    subject = _replace_variables(template_subject, variables)
    body    = _replace_variables(template_body, variables)
    return subject, body


def render_for_contact(
    step: str,
    contact: Contact,
    account: GmailAccount,
) -> RenderResult:
    """Détecte la langue et le variant, charge le bon template et rend l'email."""
    language   = detect_language(contact)
    ab_variant = pick_ab_variant(contact.id)

    template_subject, template_body = load_template(step, language, ab_variant)
    subject, body = render(template_subject, template_body, contact, account, language)

    return RenderResult(subject=subject, body=body, language=language, ab_variant=ab_variant)


# ── Validations ───────────────────────────────────────────────────────────────

def _validate_step(step: str) -> None:
    if step.strip().lower() not in _SUPPORTED_STEPS:
        raise ValueError(f"Step de template non supporté : {step!r}")


def _validate_language(language: str) -> None:
    if language not in _SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Langue non supportée : {language!r}. "
            f"Valeurs possibles : {sorted(_SUPPORTED_LANGUAGES)}"
        )


def _validate_variant(ab_variant: str) -> None:
    if ab_variant not in _SUPPORTED_VARIANTS:
        raise ValueError(
            f"Variant A/B non supporté : {ab_variant!r}. "
            f"Valeurs possibles : {sorted(_SUPPORTED_VARIANTS)}"
        )


# ── Construction des variables ────────────────────────────────────────────────

def _build_variables(
    contact: Contact,
    account: GmailAccount,
    language: str,
) -> dict[str, str]:
    first_name   = _as_text(getattr(contact, "first_name", None))
    last_name    = _as_text(getattr(contact, "last_name",  None))
    full_name    = " ".join(p for p in [first_name, last_name] if p).strip()
    company_name = _resolve_company_name(contact)
    sex          = _as_text(getattr(contact, "sex", None)).lower()
    civilite     = _resolve_civility(sex, language)

    return {
        "first_name":   first_name,
        "last_name":    last_name,
        "full_name":    full_name,
        "sex":          sex,
        "sexe":         sex,          # alias français
        "civilite":     civilite,
        "company":      company_name,
        "job_title":    _as_text(getattr(contact, "job_title", None)),
        "sender_name":  _load_sender_name(),
        "sender_email": _as_text(account.email),
    }


def _resolve_company_name(contact: Contact) -> str:
    company = getattr(contact, "company", None)
    if company is None:
        return ""
    return _as_text(getattr(company, "name", None))


def _resolve_civility(sex: str, language: str) -> str:
    """Retourne la civilité dans la bonne langue.

    FR : Monsieur / Madame
    EN : Mr. / Ms.
    Sexe ambigu ou inconnu → chaîne vide.
    """
    if language == "fr":
        if sex == "homme": return "Monsieur"
        if sex == "femme": return "Madame"
        return ""
    else:
        if sex == "homme": return "Mr."
        if sex == "femme": return "Ms."
        return ""


# ── Remplacement des variables ────────────────────────────────────────────────

def _replace_variables(template: str, variables: dict[str, str]) -> str:
    unknown: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in variables:
            return variables[key]
        unknown.add(key)
        return match.group(0)

    rendered = _VARIABLE_PATTERN.sub(_replace, template)
    for key in sorted(unknown):
        logger.warning("Variable de template inconnue laissée intacte : {{%s}}", key)
    return rendered


# ── Chargement du nom de l'expéditeur ─────────────────────────────────────────

def _load_sender_name() -> str:
    settings_payload = _load_json_settings()
    from_settings = _as_text(settings_payload.get("sender_name"))
    if from_settings:
        return from_settings

    from_env_file = _load_sender_name_from_env_file()
    if from_env_file:
        return from_env_file

    from_env = _as_text(os.getenv("SENDER_NAME"))
    if from_env:
        return from_env
    return ""


def _load_json_settings() -> dict[str, object]:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        payload = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_sender_name_from_env_file() -> str:
    if not _ENV_PATH.exists():
        return ""
    try:
        lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip().upper() != "SENDER_NAME":
            continue
        return _as_text(value.strip().strip('"').strip("'"))
    return ""


# ── Conversion Markdown → HTML ────────────────────────────────────────────────

def _markdown_to_html(content: str) -> str:
    if not content:
        return ""
    try:
        import markdown  # type: ignore
        return markdown.markdown(content)
    except Exception:
        logger.debug("Conversion markdown indisponible, body conservé en texte brut.")
        return content


# ── Utilitaire ────────────────────────────────────────────────────────────────

def _as_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()
