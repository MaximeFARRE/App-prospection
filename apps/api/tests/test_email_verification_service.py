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
        "resolved_quickemailverification_api_key",
        property(lambda _self: "test-key"),
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
        "resolved_quickemailverification_api_key",
        property(lambda _self: "test-key"),
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
