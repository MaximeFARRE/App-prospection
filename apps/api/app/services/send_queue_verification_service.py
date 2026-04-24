from __future__ import annotations

import logging

from app.services.campaign_prepare_service import QueuedEmail
from app.services.email_verification_service import (
    EmailVerificationDecision,
    verify_email_for_send,
)
from app.utils.email_normalization import normalize_email


logger = logging.getLogger(__name__)


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

    email_raw = item.contact.email or ""
    email_norm = normalize_email(email_raw)
    if not email_norm:
        return False, api_limit_reached, "invalid_or_missing_email"

    decision = decision_cache.get(email_norm)
    if decision is None:
        decision = verify_email_for_send(email_norm)
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
    """Filtre la queue d'envoi selon la vérification QuickEmailVerification.

    Règles:
    - Email non vérifié => retiré de la queue.
    - Si limite API atteinte (quota/rate-limit), on bypass ensuite toutes les
      vérifications restantes et on conserve la queue telle quelle.
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
