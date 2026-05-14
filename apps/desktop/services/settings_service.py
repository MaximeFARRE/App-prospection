from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SETTINGS_PATH = _PROJECT_ROOT / "data" / "settings.json"
_CREDENTIALS_PATH = _PROJECT_ROOT / "data" / "secure" / "credentials.json"

_LIMIT_KEYS = (
    "daily_send_limit_per_account",
    "hourly_send_limit_per_account",
    "min_delay_between_sends_sec",
    "max_delay_between_sends_sec",
    "company_weekly_send_limit",
    "gmail_weight_1",
    "gmail_weight_2",
    "gmail_weight_3",
)

_CREDENTIAL_KEYS = (
    "gmail_client_id_1", "gmail_client_secret_1", "gmail_refresh_token_1", "gmail_email_1",
    "gmail_client_id_2", "gmail_client_secret_2", "gmail_refresh_token_2", "gmail_email_2",
    "gmail_client_id_3", "gmail_client_secret_3", "gmail_refresh_token_3", "gmail_email_3",
    "quickemailverification_api_key", "quickemailverification_api_key_2",
    "sender_name",
)


def get_settings() -> dict[str, Any]:
    payload = _load_json()
    defaults = {
        "daily_send_limit_per_account":  settings.daily_send_limit_per_account,
        "hourly_send_limit_per_account": settings.hourly_send_limit_per_account,
        "min_delay_between_sends_sec":   settings.min_delay_between_sends_sec,
        "max_delay_between_sends_sec":   settings.max_delay_between_sends_sec,
        "company_weekly_send_limit":     settings.company_weekly_send_limit,
        "gmail_weight_1":                settings.gmail_weight_1,
        "gmail_weight_2":                settings.gmail_weight_2,
        "gmail_weight_3":                settings.gmail_weight_3,
        "last_gmail_sync_at": None,
    }
    for key in _LIMIT_KEYS:
        if key in payload:
            defaults[key] = int(payload[key])
    if "last_gmail_sync_at" in payload:
        defaults["last_gmail_sync_at"] = payload["last_gmail_sync_at"]
    return defaults


def set_setting(key: str, value: Any) -> None:
    payload = _load_json()
    payload[key] = value
    save_settings(payload)


def save_settings(values: dict[str, Any]) -> None:
    payload = _load_json()
    payload.update(values)
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_credentials(values: dict[str, Any]) -> None:
    existing = _load_credentials_json()
    existing.update(values)
    _CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CREDENTIALS_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_credentials() -> dict[str, Any]:
    return _load_credentials_json()


def apply_runtime_overrides() -> None:
    cfg = get_settings()
    daily   = max(1, int(cfg["daily_send_limit_per_account"]))
    hourly  = max(1, int(cfg["hourly_send_limit_per_account"]))
    minimum = max(1, int(cfg["min_delay_between_sends_sec"]))
    maximum = int(cfg["max_delay_between_sends_sec"])
    if maximum <= minimum:
        maximum = minimum + 1
    company_weekly = max(1, int(cfg["company_weekly_send_limit"]))
    weight_1 = max(1, int(cfg["gmail_weight_1"]))
    weight_2 = max(1, int(cfg["gmail_weight_2"]))
    weight_3 = max(1, int(cfg["gmail_weight_3"]))

    settings.daily_send_limit_per_account  = daily
    settings.hourly_send_limit_per_account = hourly
    settings.min_delay_between_sends_sec   = minimum
    settings.max_delay_between_sends_sec   = maximum
    settings.company_weekly_send_limit     = company_weekly
    settings.gmail_weight_1               = weight_1
    settings.gmail_weight_2               = weight_2
    settings.gmail_weight_3               = weight_3

    creds = load_credentials()
    for key in _CREDENTIAL_KEYS:
        if key in creds and creds[key]:
            setattr(settings, key, creds[key])

    save_settings({
        "daily_send_limit_per_account":  daily,
        "hourly_send_limit_per_account": hourly,
        "min_delay_between_sends_sec":   minimum,
        "max_delay_between_sends_sec":   maximum,
        "company_weekly_send_limit":     company_weekly,
        "gmail_weight_1":                weight_1,
        "gmail_weight_2":                weight_2,
        "gmail_weight_3":                weight_3,
    })


def _load_credentials_json() -> dict[str, Any]:
    if not _CREDENTIALS_PATH.exists():
        return {}
    try:
        raw = json.loads(_CREDENTIALS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def _load_json() -> dict[str, Any]:
    if not _SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw

