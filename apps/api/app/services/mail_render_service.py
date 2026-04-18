from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from app.core.config import GmailAccount
from app.models.contact import Contact


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_TEMPLATES_DIR = _PROJECT_ROOT / "data" / "templates"
_SETTINGS_PATH = _PROJECT_ROOT / "data" / "settings.json"
_ENV_PATH = _PROJECT_ROOT / ".env"
_SUPPORTED_STEPS = {"intro", "followup_1", "followup_2"}
_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z0-9_]+)\s*}}")


def load_template(step: str) -> tuple[str, str]:
    step_name = _normalize_step(step)
    template_path = _TEMPLATES_DIR / f"{step_name}.md"
    raw = template_path.read_text(encoding="utf-8")

    lines = raw.splitlines()
    if not lines:
        raise ValueError(f"Template vide: {template_path}")

    first_line = lines[0].strip()
    if not first_line.lower().startswith("subject:"):
        raise ValueError(
            f"Template invalide ({template_path}): première ligne attendue 'Subject: ...'"
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
) -> tuple[str, str]:
    variables = _build_variables(contact, account)
    subject = _replace_variables(template_subject, variables)
    body = _replace_variables(template_body, variables)
    return subject, body


def render_for_contact(step: str, contact: Contact, account: GmailAccount) -> tuple[str, str]:
    template_subject, template_body = load_template(step)
    return render(template_subject, template_body, contact, account)


def _normalize_step(step: str) -> str:
    normalized = step.strip().lower()
    if normalized not in _SUPPORTED_STEPS:
        raise ValueError(f"Step de template non supporté: {step!r}")
    return normalized


def _build_variables(contact: Contact, account: GmailAccount) -> dict[str, str]:
    first_name = _as_text(getattr(contact, "first_name", None))
    last_name = _as_text(getattr(contact, "last_name", None))
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    company_name = _resolve_company_name(contact)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "company": company_name,
        "job_title": _as_text(getattr(contact, "job_title", None)),
        "sender_name": _load_sender_name(),
        "sender_email": _as_text(account.email),
    }


def _resolve_company_name(contact: Contact) -> str:
    company = getattr(contact, "company", None)
    if company is None:
        return ""
    return _as_text(getattr(company, "name", None))


def _replace_variables(template: str, variables: dict[str, str]) -> str:
    unknown_variables: set[str] = set()

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key in variables:
            return variables[key]
        unknown_variables.add(key)
        return match.group(0)

    rendered = _VARIABLE_PATTERN.sub(_replace, template)
    for key in sorted(unknown_variables):
        logger.warning("Variable de template inconnue laissée intacte: {{%s}}", key)
    return rendered


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
    if not isinstance(payload, dict):
        return {}
    return payload


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
        cleaned = value.strip().strip('"').strip("'")
        return _as_text(cleaned)
    return ""


def _markdown_to_html(content: str) -> str:
    if not content:
        return ""
    try:
        import markdown  # type: ignore

        return markdown.markdown(content)
    except Exception:
        logger.debug("Conversion markdown indisponible, body conservé en texte brut.")
        return content


def _as_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()
