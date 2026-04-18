from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import GmailAccount, settings
from app.models.company import Company
from app.models.contact import Contact
from app.services.eligibility_service import EligibilityResult, check_eligibility
from app.services.mail_render_service import render_for_contact


@dataclass(slots=True)
class QueuedEmail:
    contact: Contact
    account: GmailAccount
    step: str
    subject: str
    body: str


@dataclass(slots=True)
class PrepareResult:
    campaign_name: str
    queue: list[QueuedEmail]
    skipped: list[EligibilityResult]
    total_contacts: int


def prepare_campaign(campaign_name: str, db: Session, dry_run: bool = False) -> PrepareResult:
    _ = dry_run  # orchestration pure: aucun write dans cette étape, même hors dry-run

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

    queue: list[QueuedEmail] = []
    skipped: list[EligibilityResult] = []
    account_idx = 0

    for contact in contacts:
        eligibility = check_eligibility(contact, db, campaign_name)
        if not eligibility.eligible:
            skipped.append(eligibility)
            continue

        if eligibility.next_step is None:
            skipped.append(
                EligibilityResult(
                    contact_id=contact.id,
                    eligible=False,
                    reason="sequence_complete",
                    next_step=None,
                )
            )
            continue

        account = accounts[account_idx % len(accounts)]
        subject, body = render_for_contact(eligibility.next_step, contact, account)
        queue.append(
            QueuedEmail(
                contact=contact,
                account=account,
                step=eligibility.next_step,
                subject=subject,
                body=body,
            )
        )
        account_idx += 1

    return PrepareResult(
        campaign_name=campaign_name,
        queue=queue,
        skipped=skipped,
        total_contacts=len(contacts),
    )


def _attach_companies(contacts: list[Contact], db: Session) -> None:
    company_ids = sorted({contact.company_id for contact in contacts if contact.company_id is not None})
    if not company_ids:
        return

    companies = db.query(Company).filter(Company.id.in_(company_ids)).all()
    company_by_id = {company.id: company for company in companies}

    for contact in contacts:
        setattr(contact, "company", company_by_id.get(contact.company_id))

