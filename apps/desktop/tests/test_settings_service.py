from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _import_service():
    from services import settings_service
    return settings_service


# ── test_save_and_load_credentials ────────────────────────────────────────────

def test_save_and_load_credentials(tmp_path: Path) -> None:
    creds_file = tmp_path / "creds.json"
    svc = _import_service()
    with patch.object(svc, "_CREDENTIALS_PATH", creds_file):
        svc.save_credentials({"sender_name": "Test"})
        result = svc.load_credentials()
    assert result["sender_name"] == "Test"


# ── test_save_credentials_merges ─────────────────────────────────────────────

def test_save_credentials_merges(tmp_path: Path) -> None:
    creds_file = tmp_path / "creds.json"
    svc = _import_service()
    with patch.object(svc, "_CREDENTIALS_PATH", creds_file):
        svc.save_credentials({"sender_name": "Alice"})
        svc.save_credentials({"sender_website": "https://alice.dev"})
        result = svc.load_credentials()
    assert result["sender_name"] == "Alice"
    assert result["sender_website"] == "https://alice.dev"


# ── test_load_credentials_missing_file ───────────────────────────────────────

def test_load_credentials_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.json"
    svc = _import_service()
    with patch.object(svc, "_CREDENTIALS_PATH", missing):
        result = svc.load_credentials()
    assert result == {}
