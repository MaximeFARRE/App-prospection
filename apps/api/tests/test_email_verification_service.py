from __future__ import annotations

import pytest

from app.services import email_verification_service


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return dict(self._payload)


def test_verify_email_for_send_returns_limit_reached_on_402(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        type(email_verification_service.settings),
        "resolved_quickemailverification_api_keys",
        property(lambda _self: ["test-key"]),
    )
    monkeypatch.setattr(
        email_verification_service.httpx,
        "get",
        lambda *args, **kwargs: _FakeResponse(402, {}),
    )

    decision = email_verification_service.verify_email_for_send("a@example.com")

    assert decision.can_send is True
    assert decision.api_limit_reached is True


def test_verify_email_for_send_blocks_email_when_safe_to_send_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        type(email_verification_service.settings),
        "resolved_quickemailverification_api_keys",
        property(lambda _self: ["test-key"]),
    )
    monkeypatch.setattr(
        email_verification_service.httpx,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            200,
            {
                "success": True,
                "result": "invalid",
                "reason": "rejected_email",
                "safe_to_send": False,
            },
        ),
    )

    decision = email_verification_service.verify_email_for_send("blocked@example.com")

    assert decision.can_send is False
    assert decision.api_limit_reached is False
    assert decision.reason == "safe_to_send_false"


def test_verify_email_for_send_falls_back_to_second_key_after_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        type(email_verification_service.settings),
        "resolved_quickemailverification_api_keys",
        property(lambda _self: ["key-1", "key-2"]),
    )

    calls: list[str] = []

    def _fake_get(*args, **kwargs):
        calls.append(str(kwargs["params"]["apikey"]))
        if len(calls) == 1:
            return _FakeResponse(402, {})
        return _FakeResponse(
            200,
            {
                "success": True,
                "result": "valid",
                "reason": "accepted_email",
                "safe_to_send": True,
            },
        )

    monkeypatch.setattr(email_verification_service.httpx, "get", _fake_get)

    decision = email_verification_service.verify_email_for_send("ok@example.com")

    assert calls == ["key-1", "key-2"]
    assert decision.can_send is True
    assert decision.api_limit_reached is False
    assert decision.reason == "safe_to_send_true"
    assert decision.provider_result == "valid"


def test_verify_email_for_send_returns_limit_when_all_keys_are_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        type(email_verification_service.settings),
        "resolved_quickemailverification_api_keys",
        property(lambda _self: ["key-1", "key-2"]),
    )
    monkeypatch.setattr(
        email_verification_service.httpx,
        "get",
        lambda *args, **kwargs: _FakeResponse(429, {}),
    )

    decision = email_verification_service.verify_email_for_send("limited@example.com")

    assert decision.can_send is True
    assert decision.api_limit_reached is True
    assert decision.reason == "api_limit_status_429"
