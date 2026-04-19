from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import GmailAccount, settings
from app.models.company import Company
from app.models.contact import Contact
from app.models.message import Message
from app.services.eligibility_service import EligibilityResult, check_eligibility
from app.services.mail_render_service import detect_language, render_for_contact


# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass(slots=True)
class QueuedEmail:
    contact: Contact
    account: GmailAccount
    step: str
    subject: str
    body: str
    language: str    # "fr" ou "en"
    ab_variant: str  # variant du template utilisé


@dataclass(slots=True)
class CampaignStats:
    total: int
    fr_count: int
    en_count: int
    companies_count: int
    step_counts: dict[str, int]           # {"intro": X, "followup_1": Y, ...}
    account_distribution: dict[str, int]  # {email: nb_mails}
    estimated_min_days: int
    estimated_max_days: int
    skipped_total: int
    skipped_reasons: dict[str, int]       # {"blocked": 3, "replied": 1, ...}


@dataclass(slots=True)
class PrepareResult:
    campaign_name: str
    queue: list[QueuedEmail]
    skipped: list[EligibilityResult]
    total_contacts: int
    stats: CampaignStats


# ── Point d'entrée public ─────────────────────────────────────────────────────

def prepare_campaign(campaign_name: str, db: Session, dry_run: bool = False) -> PrepareResult:
    _ = dry_run  # orchestration pure : aucun write dans cette étape

    accounts = settings.configured_gmail_accounts
    if not accounts:
        raise RuntimeError("Aucun compte Gmail configuré pour préparer la campagne.")

    contacts = (
        db.query(Contact)
        .filter(Contact.is_blocked.is_(False))
        .order_by(Contact.id.asc())
        .all()
    )
    _attach_companies(contacts, db)

    # Poids de répartition entre comptes (round-robin pondéré)
    weights = _build_account_weights(accounts)

    # Offsets pour la rotation des templates (reprend là où on s'est arrêté)
    sent_offsets = _load_sent_offsets(campaign_name, db)

    queue: list[QueuedEmail] = []
    skipped: list[EligibilityResult] = []

    # Compteurs de position par (step, langue) pour la rotation round-robin
    position_counters: dict[tuple[str, str], int] = {}

    for contact in contacts:
        eligibility = check_eligibility(contact, db, campaign_name)
        if not eligibility.eligible or eligibility.next_step is None:
            skipped.append(eligibility)
            continue

        step     = eligibility.next_step
        language = detect_language(contact)
        key      = (step, language)

        # Position absolue = déjà envoyés + position dans la queue courante
        offset   = sent_offsets.get(key, 0)
        counter  = position_counters.get(key, 0)
        position = offset + counter

        account = random.choices(accounts, weights=weights, k=1)[0]
        result  = render_for_contact(step, contact, account, position=position)

        queue.append(
            QueuedEmail(
                contact=contact,
                account=account,
                step=step,
                subject=result.subject,
                body=result.body,
                language=result.language,
                ab_variant=result.ab_variant,
            )
        )
        position_counters[key] = counter + 1

    stats = _compute_stats(queue, skipped, accounts)
    return PrepareResult(
        campaign_name=campaign_name,
        queue=queue,
        skipped=skipped,
        total_contacts=len(contacts),
        stats=stats,
    )


# ── Helpers internes ──────────────────────────────────────────────────────────

def _build_account_weights(accounts: list[GmailAccount]) -> list[float]:
    """Retourne la liste de poids correspondant aux comptes configurés.

    Lit gmail_weight_1, gmail_weight_2, gmail_weight_3… pour chaque slot.
    Les poids n'ont pas besoin de sommer à 100 : random.choices les normalise.
    """
    weights = []
    for i in range(1, len(accounts) + 1):
        w = max(1, int(getattr(settings, f"gmail_weight_{i}", 50)))
        weights.append(float(w))
    return weights


def _load_sent_offsets(
    campaign_name: str,
    db: Session,
) -> dict[tuple[str, str], int]:
    """Compte les messages déjà envoyés par (step, langue) pour cette campagne.

    Sert d'offset pour la rotation round-robin lors d'une reprise.
    """
    rows = (
        db.query(Message.message_type, Message.language, func.count(Message.id))
        .filter(
            Message.campaign_name == campaign_name,
            Message.message_type.in_(["intro", "followup_1", "followup_2"]),
            Message.language.isnot(None),
        )
        .group_by(Message.message_type, Message.language)
        .all()
    )
    return {(step, lang): int(count) for step, lang, count in rows}


def _compute_stats(
    queue: list[QueuedEmail],
    skipped: list[EligibilityResult],
    accounts: list[GmailAccount],
) -> CampaignStats:
    total = len(queue)

    fr_count = sum(1 for q in queue if q.language == "fr")
    en_count = total - fr_count

    companies = {
        q.contact.company_id
        for q in queue
        if getattr(q.contact, "company_id", None) is not None
    }

    step_counts: dict[str, int] = {}
    for q in queue:
        step_counts[q.step] = step_counts.get(q.step, 0) + 1

    account_dist: dict[str, int] = {}
    for q in queue:
        account_dist[q.account.email] = account_dist.get(q.account.email, 0) + 1

    # Estimation de durée (contrainte journalière)
    daily_capacity = max(1, settings.daily_send_limit_per_account) * len(accounts)
    estimated_min_days = max(1, math.ceil(total / daily_capacity)) if total > 0 else 0

    # Estimation max : on ajoute 20 % de marge pour les délais et pauses horaires
    estimated_max_days = max(estimated_min_days, math.ceil(estimated_min_days * 1.2))

    skipped_reasons: dict[str, int] = {}
    for s in skipped:
        skipped_reasons[s.reason] = skipped_reasons.get(s.reason, 0) + 1

    return CampaignStats(
        total=total,
        fr_count=fr_count,
        en_count=en_count,
        companies_count=len(companies),
        step_counts=step_counts,
        account_distribution=account_dist,
        estimated_min_days=estimated_min_days,
        estimated_max_days=estimated_max_days,
        skipped_total=len(skipped),
        skipped_reasons=skipped_reasons,
    )


def _attach_companies(contacts: list[Contact], db: Session) -> None:
    company_ids = sorted({c.company_id for c in contacts if c.company_id is not None})
    if not company_ids:
        return
    companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
    company_by_id = {co.id: co for co in companies}
    for contact in contacts:
        setattr(contact, "company", company_by_id.get(contact.company_id))
