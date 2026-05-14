from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.campaign_prepare_service import PrepareResult, prepare_campaign

FOLLOWUP_STEPS = frozenset({"followup_1", "followup_2"})


def prepare_followups(campaign_name: str, db: Session, dry_run: bool = False) -> PrepareResult:
    """Prepare uniquement la file des relances d'une campagne.

    La logique d'eligibilite (dont le delai de 7 jours et le next_step) reste
    centralisee dans eligibility_service via prepare_campaign.
    """

    prepared = prepare_campaign(campaign_name=campaign_name, db=db, dry_run=dry_run)
    queue = [queued_email for queued_email in prepared.queue if queued_email.step in FOLLOWUP_STEPS]

    return PrepareResult(
        campaign_name=prepared.campaign_name,
        queue=queue,
        skipped=prepared.skipped,
        total_contacts=prepared.total_contacts,
        stats=prepared.stats,
    )
