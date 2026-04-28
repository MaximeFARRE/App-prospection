from __future__ import annotations

from dataclasses import dataclass
import logging

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)

_QEV_VERIFY_URL = "https://api.quickemailverification.com/v1/verify"
_LIMIT_STATUS_CODES = {402, 429}
_LIMIT_HINTS = (
    "credit limit",
    "rate limit",
    "too many requests",
    "limit reached",
    "running out of your credit",
)


@dataclass(slots=True)
class EmailVerificationDecision:
    can_send: bool
    api_limit_reached: bool
    reason: str
    provider_result: str | None = None


def verify_email_for_send(email: str) -> EmailVerificationDecision:
    """Vérifie un email via QuickEmailVerification pour décider l'envoi.

    Règle produit:
    - can_send=False si l'email n'est pas vérifié comme sûr.
    - api_limit_reached=True si quota/rate-limit atteint ; dans ce cas l'appelant
      doit bypass la vérification et poursuivre les envois.
    """
    api_keys = settings.resolved_quickemailverification_api_keys
    if not api_keys:
        logger.warning(
            "QuickEmailVerification non configuré (clé absente). "
            "Vérification ignorée pour %s.",
            email,
        )
        return EmailVerificationDecision(
            can_send=True,
            api_limit_reached=False,
            reason="verification_disabled_missing_api_key",
        )

    timeout = max(1, int(settings.quickemailverification_timeout_sec))
    last_limit_decision: EmailVerificationDecision | None = None
    for index, api_key in enumerate(api_keys, start=1):
        decision = _verify_with_single_api_key(email=email, api_key=api_key, timeout=timeout)
        if not decision.api_limit_reached:
            return decision

        last_limit_decision = decision
        if index < len(api_keys):
            logger.warning(
                "Limite QuickEmailVerification atteinte avec la clé #%s, bascule vers la clé suivante.",
                index,
            )
            continue

    return last_limit_decision or EmailVerificationDecision(
        can_send=True,
        api_limit_reached=True,
        reason="api_limit_reached_all_keys",
    )


def _verify_with_single_api_key(
    *,
    email: str,
    api_key: str,
    timeout: int,
) -> EmailVerificationDecision:
    try:
        response = httpx.get(
            _QEV_VERIFY_URL,
            params={"email": email, "apikey": api_key},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return EmailVerificationDecision(
            can_send=False,
            api_limit_reached=False,
            reason=f"http_error:{exc.__class__.__name__}",
        )

    if response.status_code in _LIMIT_STATUS_CODES:
        return EmailVerificationDecision(
            can_send=True,
            api_limit_reached=True,
            reason=f"api_limit_status_{response.status_code}",
        )

    if response.status_code != 200:
        return EmailVerificationDecision(
            can_send=False,
            api_limit_reached=False,
            reason=f"http_status_{response.status_code}",
        )

    try:
        body = response.json()
    except ValueError:
        return EmailVerificationDecision(
            can_send=False,
            api_limit_reached=False,
            reason="invalid_json_response",
        )

    success = bool(body.get("success"))
    message = str(body.get("message") or "").strip()
    if not success:
        if _is_limit_message(message):
            return EmailVerificationDecision(
                can_send=True,
                api_limit_reached=True,
                reason="api_limit_message",
            )
        return EmailVerificationDecision(
            can_send=False,
            api_limit_reached=False,
            reason=message or "provider_failed",
        )

    provider_result = str(body.get("result") or "").strip().lower() or None
    safe_to_send = body.get("safe_to_send")
    if isinstance(safe_to_send, bool):
        return EmailVerificationDecision(
            can_send=safe_to_send,
            api_limit_reached=False,
            reason="safe_to_send_true" if safe_to_send else "safe_to_send_false",
            provider_result=provider_result,
        )

    # Fallback legacy: certains environnements renvoient surtout result/reason.
    provider_reason = str(body.get("reason") or "").strip().lower()
    accepted = provider_result == "valid" and provider_reason == "accepted_email"
    return EmailVerificationDecision(
        can_send=accepted,
        api_limit_reached=False,
        reason="accepted_email" if accepted else (provider_reason or "not_verified"),
        provider_result=provider_result,
    )


def _is_limit_message(message: str) -> bool:
    text = message.strip().lower()
    if not text:
        return False
    return any(hint in text for hint in _LIMIT_HINTS)
