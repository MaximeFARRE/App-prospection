"""Tests SupabaseRepository — client Supabase mocké via MagicMock."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest

from app.repositories.supabase_repository import SupabaseRepository, _hash_email


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fluent(data=None, count: int = 0):
    """Mock client Supabase dont toute la chaîne retourne lui-même jusqu'à execute()."""
    client = MagicMock()
    response = SimpleNamespace(data=data, count=count)
    # Toute la chaîne fluide retourne le même mock
    for attr in ("table", "select", "eq", "gte", "in_", "single",
                 "limit", "upsert", "insert"):
        getattr(client, attr).return_value = client
    client.execute.return_value = response
    return client, response


def _repo(client=None) -> SupabaseRepository:
    if client is None:
        client, _ = _fluent()
    return SupabaseRepository(client)


# ── _hash_email ───────────────────────────────────────────────────────────────

def test_hash_email_consistent() -> None:
    assert _hash_email("Alice@ACME.com") == _hash_email("alice@acme.com")
    assert _hash_email("  test@x.com  ") == _hash_email("test@x.com")


def test_hash_email_returns_64_char_hex() -> None:
    h = _hash_email("test@example.com")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


# ── get_user_credits ──────────────────────────────────────────────────────────

def test_get_user_credits_returns_int() -> None:
    client, resp = _fluent(data={"credits": 42})
    assert _repo(client).get_user_credits("uid-1") == 42


def test_get_user_credits_returns_zero_on_missing_field() -> None:
    client, _ = _fluent(data={})
    assert _repo(client).get_user_credits("uid-1") == 0


def test_get_user_credits_returns_zero_on_network_error() -> None:
    client, _ = _fluent()
    client.execute.side_effect = Exception("network error")
    assert _repo(client).get_user_credits("uid-1") == 0


# ── get_unlocked_count ────────────────────────────────────────────────────────

def test_get_unlocked_count_returns_count() -> None:
    client, _ = _fluent(data=[], count=7)
    assert _repo(client).get_unlocked_count("uid-1") == 7


def test_get_unlocked_count_returns_zero_on_error() -> None:
    client, _ = _fluent()
    client.execute.side_effect = RuntimeError("timeout")
    assert _repo(client).get_unlocked_count("uid-1") == 0


# ── upsert_contact ────────────────────────────────────────────────────────────

def test_upsert_contact_returns_supabase_id() -> None:
    client, _ = _fluent(data=[{"id": "supa-uuid-abc"}])
    repo = _repo(client)
    result = repo.upsert_contact("alice@corp.com", {"first_name": "Alice"})
    assert result == "supa-uuid-abc"


def test_upsert_contact_never_sends_email_in_payload() -> None:
    client, _ = _fluent(data=[{"id": "x"}])
    repo = _repo(client)
    repo.upsert_contact("alice@corp.com", {"email": "alice@corp.com", "first_name": "Alice"})
    # Récupère le payload passé à upsert()
    call_kwargs = client.upsert.call_args
    payload = call_kwargs[0][0]  # premier arg positionnel
    assert "email" not in payload
    assert "email_hash" in payload


def test_upsert_contact_idempotent_uses_on_conflict() -> None:
    client, _ = _fluent(data=[{"id": "x"}])
    repo = _repo(client)
    repo.upsert_contact("alice@corp.com", {})
    client.upsert.assert_called_once()
    _, kwargs = client.upsert.call_args
    assert kwargs.get("on_conflict") == "email_hash"


def test_upsert_contact_returns_none_on_error() -> None:
    client, _ = _fluent()
    client.execute.side_effect = Exception("DB error")
    assert _repo(client).upsert_contact("a@b.com", {}) is None


# ── check_already_contacted ───────────────────────────────────────────────────

def test_check_already_contacted_batch() -> None:
    emails = ["alice@corp.com", "bob@corp.com"]
    h_alice = _hash_email("alice@corp.com")
    client, _ = _fluent(data=[{"email_hash": h_alice}])
    repo = _repo(client)

    result = repo.check_already_contacted(emails)

    assert result == {h_alice}
    # Vérifie que in_() a reçu les deux hashes
    in_call_args = client.in_.call_args[0]
    assert _hash_email("alice@corp.com") in in_call_args[1]
    assert _hash_email("bob@corp.com") in in_call_args[1]


def test_check_already_contacted_empty_list_returns_empty_set() -> None:
    client, _ = _fluent(data=[])
    assert _repo(client).check_already_contacted([]) == set()
    client.execute.assert_not_called()


def test_check_already_contacted_returns_empty_on_error() -> None:
    client, _ = _fluent()
    client.execute.side_effect = Exception("network")
    assert _repo(client).check_already_contacted(["a@b.com"]) == set()


# ── request_unlock ────────────────────────────────────────────────────────────

def test_request_unlock_respects_count() -> None:
    candidate = {"id": "c1", "email_hash": _hash_email("x@y.com"), "first_name": "X"}
    client = MagicMock()
    # Chaîne fluide
    for attr in ("table", "select", "eq", "limit", "insert"):
        getattr(client, attr).return_value = client
    # Trois appels successifs à execute() :
    # 1) already_ids → aucun débloqué
    # 2) candidates → un contact
    # 3) insert unlocks → ignoré
    client.execute.side_effect = [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[candidate]),
        SimpleNamespace(data=[]),
    ]
    repo = _repo(client)
    result = repo.request_unlock("uid-1", 1)
    assert result == [candidate]


def test_request_unlock_returns_empty_on_error() -> None:
    client, _ = _fluent()
    client.execute.side_effect = Exception("timeout")
    assert _repo(client).request_unlock("uid-1", 3) == []


# ── record_contact_event ──────────────────────────────────────────────────────

def test_record_contact_event_hashes_email() -> None:
    client, _ = _fluent(data=[])
    repo = _repo(client)
    repo.record_contact_event("Alice@CORP.com", "contacted", "uid-1")

    insert_call = client.insert.call_args[0][0]
    assert insert_call["email_hash"] == _hash_email("alice@corp.com")
    assert insert_call["event_type"] == "contacted"
    assert insert_call["user_id"] == "uid-1"


def test_repo_returns_empty_on_network_error() -> None:
    """Toutes les méthodes retournent une valeur nulle sur erreur réseau."""
    client, _ = _fluent()
    client.execute.side_effect = Exception("network down")
    repo = _repo(client)

    assert repo.get_user_credits("u") == 0
    assert repo.get_unlocked_count("u") == 0
    assert repo.get_unlocked_contacts("u") == []
    assert repo.upsert_contact("a@b.com", {}) is None
    assert repo.create_contribution("u", "c") is False
    assert repo.request_unlock("u", 1) == []
    assert repo.check_already_contacted(["a@b.com"]) == set()
