from __future__ import annotations

import logging

from app.services.campaign_prepare_service import QueuedEmail
from app.services.email_verification_service import (
    EmailVerificationDecision,
    verify_email_for_send,
)
from app.utils.email_normalization import normalize_email


logger = logging.getLogger(__name__)


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
        if api_limit_reached:
            filtered.append(item)
            continue

        email_raw = item.contact.email or ""
        email_norm = normalize_email(email_raw)
        if not email_norm:
            removed_count += 1
            logger.warning(
                "Contact retiré de la file (email invalide/non normalisable): contact_id=%s email=%s",
                item.contact.id,
                email_raw,
            )
            continue

        decision = decision_cache.get(email_norm)
        if decision is None:
            decision = verify_email_for_send(email_norm)
            decision_cache[email_norm] = decision

        if decision.api_limit_reached:
            api_limit_reached = True
            logger.warning(
                "Limite QuickEmailVerification atteinte (%s). "
                "Vérification désactivée pour le reste de la campagne.",
                decision.reason,
            )
            filtered.append(item)
            continue

        if not decision.can_send:
            removed_count += 1
            logger.warning(
                "Contact retiré de la file après vérification email: "
                "contact_id=%s email=%s reason=%s",
                item.contact.id,
                email_norm,
                decision.reason,
            )
            continue

        filtered.append(item)

    return filtered, removed_count
