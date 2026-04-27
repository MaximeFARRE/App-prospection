from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging

from app.core.config import settings
from app.models.contact import Contact
from app.services.campaign_prepare_service import QueuedEmail
from app.services.email_verification_service import (
    EmailVerificationDecision,
    verify_email_for_send,
)
from app.utils.email_normalization import normalize_email


logger = logging.getLogger(__name__)
_BLOCKING_EMAIL_STATUSES = {"valid", "invalid"}


def should_send_item_with_email_verification(
    item: QueuedEmail,
    *,
    decision_cache: dict[str, EmailVerificationDecision],
    api_limit_reached: bool,
) -> tuple[bool, bool, str]:
    """Décide si un item peut être envoyé juste avant l'envoi effectif.

    Retour:
    - should_send: True si l'item doit être envoyé.
    - api_limit_reached: état mis à jour (bypass des checks suivants).
    - reason: raison de la décision.
    """
    if api_limit_reached:
        return True, True, "api_limit_bypass"

    now = _utcnow_naive()
    email_raw = item.contact.email or ""
    email_norm = normalize_email(email_raw)
    if not email_norm:
        _apply_contact_email_state(
            item.contact,
            status="invalid",
            reason="invalid_or_missing_email",
            checked_at=now,
        )
        return False, api_limit_reached, "invalid_or_missing_email"

    decision = decision_cache.get(email_norm)
    if decision is None:
        decision = _decision_from_cached_contact_status(item.contact, now)
        if decision is not None:
            decision_cache[email_norm] = decision
    if decision is None:
        decision = verify_email_for_send(email_norm)
        _apply_contact_email_state_from_decision(item.contact, decision, now)
        decision_cache[email_norm] = decision

    if decision.api_limit_reached:
        return True, True, decision.reason

    if decision.can_send:
        return True, api_limit_reached, decision.reason

    # En cas d'erreur technique API, on n'empêche pas l'envoi.
    if _is_non_blocking_failure(decision.reason):
        return True, api_limit_reached, decision.reason

    return False, api_limit_reached, decision.reason


def filter_send_queue_with_email_verification(
    queue: list[QueuedEmail],
) -> tuple[list[QueuedEmail], int]:
    """Helper legacy: filtre une queue complète selon la vérification email.

    Règles:
    - Email non vérifié => retiré de la queue.
    - Si limite API atteinte (quota/rate-limit), on bypass ensuite toutes les
      vérifications restantes et on conserve la queue telle quelle.

    Remarque:
    - Le flux de prod doit privilégier `should_send_item_with_email_verification`
      juste avant chaque envoi (mode just-in-time).
    """
    if not queue:
        return [], 0

    filtered: list[QueuedEmail] = []
    removed_count = 0
    api_limit_reached = False
    decision_cache: dict[str, EmailVerificationDecision] = {}

    for item in queue:
        should_send, api_limit_reached, reason = should_send_item_with_email_verification(
            item,
            decision_cache=decision_cache,
            api_limit_reached=api_limit_reached,
        )
        if should_send:
            if api_limit_reached and reason != "api_limit_bypass":
                logger.warning(
                    "Limite QuickEmailVerification atteinte (%s). "
                    "Vérification désactivée pour le reste de la campagne.",
                    reason,
                )
            filtered.append(item)
            continue

        removed_count += 1
        logger.warning(
            "Contact retiré de la file après vérification email: "
            "contact_id=%s email=%s reason=%s",
            item.contact.id,
            item.contact.email,
            reason,
        )

    return filtered, removed_count


def _is_non_blocking_failure(reason: str) -> bool:
    if reason.startswith("http_error:"):
        return True
    if reason.startswith("http_status_"):
        return True
    return reason in {"invalid_json_response", "provider_failed"}


def _decision_from_cached_contact_status(
    contact: Contact,
    now: datetime,
) -> EmailVerificationDecision | None:
    status = _normalize_email_status(contact.email_status)
    if status not in _BLOCKING_EMAIL_STATUSES:
        return None

    checked_at = contact.email_checked_at
    if checked_at is None:
        return None

    ttl_days = max(0, int(settings.email_verification_ttl_days))
    if ttl_days <= 0:
        return None
    if checked_at + timedelta(days=ttl_days) < now:
        return None

    reason = str(contact.email_check_reason or f"cached_status_{status}")
    return EmailVerificationDecision(
        can_send=(status == "valid"),
        api_limit_reached=False,
        reason=reason,
        provider_result=status,
    )


def _apply_contact_email_state_from_decision(
    contact: Contact,
    decision: EmailVerificationDecision,
    checked_at: datetime,
) -> None:
    if decision.api_limit_reached:
        return
    if decision.can_send:
        if decision.reason.startswith("verification_disabled_"):
            _apply_contact_email_state(
                contact,
                status="unknown",
                reason=decision.reason,
                checked_at=checked_at,
            )
            return
        _apply_contact_email_state(
            contact,
            status="valid",
            reason=decision.reason,
            checked_at=checked_at,
        )
        return
    if _is_non_blocking_failure(decision.reason):
        _apply_contact_email_state(
            contact,
            status="unknown",
            reason=decision.reason,
            checked_at=checked_at,
        )
        return
    _apply_contact_email_state(
        contact,
        status="invalid",
        reason=decision.reason,
        checked_at=checked_at,
    )


def _apply_contact_email_state(
    contact: Contact,
    *,
    status: str,
    reason: str,
    checked_at: datetime,
) -> None:
    contact.email_status = _normalize_email_status(status)
    contact.email_check_reason = reason[:255]
    contact.email_checked_at = checked_at


def _normalize_email_status(status: str | None) -> str | None:
    if status is None:
        return None
    normalized = str(status).strip().lower()
    if not normalized:
        return None
    return normalized


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
