from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SETTINGS_PATH = _PROJECT_ROOT / "data" / "settings.json"

_LIMIT_KEYS = (
    "daily_send_limit_per_account",
    "min_delay_between_sends_sec",
    "max_delay_between_sends_sec",
)


def get_settings() -> dict[str, Any]:
    payload = _load_json()
    defaults = {
        "daily_send_limit_per_account": settings.daily_send_limit_per_account,
        "min_delay_between_sends_sec": settings.min_delay_between_sends_sec,
        "max_delay_between_sends_sec": settings.max_delay_between_sends_sec,
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


def apply_runtime_overrides() -> None:
    cfg = get_settings()
    daily = max(1, int(cfg["daily_send_limit_per_account"]))
    minimum = max(1, int(cfg["min_delay_between_sends_sec"]))
    maximum = int(cfg["max_delay_between_sends_sec"])
    if maximum <= minimum:
        maximum = minimum + 1

    settings.daily_send_limit_per_account = daily
    settings.min_delay_between_sends_sec = minimum
    settings.max_delay_between_sends_sec = maximum

    save_settings(
        {
            "daily_send_limit_per_account": daily,
            "min_delay_between_sends_sec": minimum,
            "max_delay_between_sends_sec": maximum,
        }
    )


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

