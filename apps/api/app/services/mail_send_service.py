from __future__ import annotations

import base64
import logging
import random
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import GmailAccount, settings
from app.models.campaign_state import CampaignState
from app.models.message import Message
from app.services.campaign_prepare_service import QueuedEmail


logger = logging.getLogger(__name__)

SEND_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SEND_TYPES = ("intro", "followup_1", "followup_2")


@dataclass(slots=True)
class SendProgress:
    total: int
    sent: int = 0
    failed: int = 0
    current_contact: str = ""


def send_campaign(
    queue: list[QueuedEmail],
    db: Session,
    campaign_name: str,
    progress_callback: Callable[[SendProgress], None] | None = None,
    stop_event: threading.Event | None = None,
) -> SendProgress:
    if not queue:
        return SendProgress(total=0)

    accounts = settings.configured_gmail_accounts
    if not accounts:
        raise RuntimeError("Aucun compte Gmail configuré pour envoyer la campagne.")

    progress = SendProgress(total=len(queue))
    service_by_email: dict[str, object] = {}
    sent_today_cache = _build_sent_today_cache(db, accounts)

    for item in queue:
        if _should_stop(stop_event):
            logger.info("Envoi interrompu par stop_event.")
            break

        progress.current_contact = _format_contact_label(item)
        account = _pick_available_account(item.account, accounts, db, sent_today_cache)
        if account is None:
            logger.warning("Limite journalière atteinte sur tous les comptes, arrêt de la campagne.")
            break

        try:
            service = _get_or_build_service(account, service_by_email)
            response = _send_message_with_retry(service, item, account)
            sent_at = datetime.utcnow()
            _record_sent_message(item, account, campaign_name, response.get("id"), sent_at, db)
            _upsert_campaign_state(item, campaign_name, sent_at, db)
            db.commit()

            progress.sent += 1
            sent_today_cache[account.email] = sent_today_cache.get(account.email, 0) + 1
            _publish_progress(progress_callback, progress)

            if _should_stop(stop_event):
                logger.info("Arrêt demandé avant la pause inter-envoi.")
                break
            _sleep_between_sends()
        except Exception as exc:  # pragma: no cover - dépend des APIs externes
            db.rollback()
            progress.failed += 1
            logger.exception("Échec envoi contact_id=%s: %s", item.contact.id, exc)
            _publish_progress(progress_callback, progress)

    return progress


def _count_sent_today(account_email: str, db: Session) -> int:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return int(
        db.query(Message.id)
        .filter(
            and_(
                Message.from_email == account_email,
                Message.sent_at >= today_start,
                Message.message_type.in_(SEND_TYPES),
            )
        )
        .count()
    )


def _build_sent_today_cache(db: Session, accounts: list[GmailAccount]) -> dict[str, int]:
    return {account.email: _count_sent_today(account.email, db) for account in accounts}


def _pick_available_account(
    preferred_account: GmailAccount,
    accounts: list[GmailAccount],
    db: Session,
    sent_today_cache: dict[str, int],
) -> GmailAccount | None:
    daily_limit = max(1, int(settings.daily_send_limit_per_account))
    ordered_accounts = [preferred_account] + [a for a in accounts if a.email != preferred_account.email]

    for account in ordered_accounts:
        if not account.email:
            continue
        current_count = sent_today_cache.get(account.email)
        if current_count is None:
            current_count = _count_sent_today(account.email, db)
            sent_today_cache[account.email] = current_count
        if current_count < daily_limit:
            return account
    return None


def _get_or_build_service(account: GmailAccount, service_by_email: dict[str, object]):
    if account.email in service_by_email:
        return service_by_email[account.email]
    service = _build_send_service(account)
    service_by_email[account.email] = service
    return service


def _build_send_service(account: GmailAccount):
    creds = Credentials(
        token=None,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account.client_id,
        client_secret=account.client_secret,
        scopes=SEND_SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _send_message_with_retry(service, item: QueuedEmail, account: GmailAccount) -> dict:
    payload = _build_raw_message(item, account)
    try:
        return service.users().messages().send(userId="me", body=payload).execute()
    except HttpError as exc:
        if not _is_quota_error(exc):
            raise
        logger.warning("Quota Gmail (429) pour %s, pause 60s puis retry.", account.email)
        time.sleep(60)
        return service.users().messages().send(userId="me", body=payload).execute()


def _build_raw_message(item: QueuedEmail, account: GmailAccount) -> dict[str, str]:
    # Conteneur principal "mixed" pour pouvoir ajouter des pièces jointes
    mime_message = MIMEMultipart("mixed")
    mime_message["To"] = item.contact.email or ""
    mime_message["From"] = account.email
    mime_message["Subject"] = item.subject

    # Corps texte + HTML dans une partie "alternative" imbriquée
    body_part = MIMEMultipart("alternative")
    plain_body = _html_to_text(item.body)
    body_part.attach(MIMEText(plain_body, "plain", "utf-8"))
    body_part.attach(MIMEText(item.body, "html", "utf-8"))
    mime_message.attach(body_part)

    # Pièce jointe CV (si le fichier existe)
    cv_path = Path(settings.cv_path)
    if cv_path.is_file():
        cv_data = cv_path.read_bytes()
        attachment = MIMEApplication(cv_data, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=cv_path.name,
        )
        mime_message.attach(attachment)
    else:
        logger.warning("CV introuvable, envoi sans pièce jointe : %s", cv_path)

    encoded = base64.urlsafe_b64encode(mime_message.as_bytes()).decode("utf-8")
    return {"raw": encoded}


def _html_to_text(content: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", content)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _record_sent_message(
    item: QueuedEmail,
    account: GmailAccount,
    campaign_name: str,
    gmail_message_id: str | None,
    sent_at: datetime,
    db: Session,
) -> None:
    db.add(
        Message(
            contact_id=item.contact.id,
            campaign_name=campaign_name,
            subject=item.subject,
            body=item.body,
            from_email=account.email,
            message_type=item.step,
            language=item.language,
            ab_variant=item.ab_variant,
            gmail_message_id=gmail_message_id,
            sent_at=sent_at,
        )
    )


def _upsert_campaign_state(
    item: QueuedEmail,
    campaign_name: str,
    sent_at: datetime,
    db: Session,
) -> None:
    state = (
        db.query(CampaignState)
        .filter(
            CampaignState.contact_id == item.contact.id,
            CampaignState.campaign_name == campaign_name,
        )
        .first()
    )
    if state is None:
        state = CampaignState(contact_id=item.contact.id, campaign_name=campaign_name)
        db.add(state)

    if item.step == "intro":
        state.intro_sent = True
        state.intro_sent_at = sent_at
    if item.step == "followup_1":
        state.followup_1_sent = True
        state.followup_1_sent_at = sent_at
    if item.step == "followup_2":
        state.followup_2_sent = True
        state.followup_2_sent_at = sent_at


def _sleep_between_sends() -> None:
    minimum = max(1, int(settings.min_delay_between_sends_sec))
    maximum = max(minimum, int(settings.max_delay_between_sends_sec))
    time.sleep(random.randint(minimum, maximum))


def _publish_progress(
    progress_callback: Callable[[SendProgress], None] | None,
    progress: SendProgress,
) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(progress)
    except Exception as exc:  # pragma: no cover - dépend du callback appelant
        logger.warning("progress_callback a levé une exception: %s", exc)


def _is_quota_error(exc: HttpError) -> bool:
    status_code = getattr(getattr(exc, "resp", None), "status", None)
    return int(status_code or 0) == 429


def _should_stop(stop_event: threading.Event | None) -> bool:
    return stop_event is not None and stop_event.is_set()


def _format_contact_label(item: QueuedEmail) -> str:
    first_name = str(getattr(item.contact, "first_name", "") or "").strip()
    last_name = str(getattr(item.contact, "last_name", "") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    company = getattr(getattr(item.contact, "company", None), "name", None)
    company_name = str(company or "").strip()

    base = full_name or (item.contact.email or f"contact#{item.contact.id}")
    if company_name:
        base = f"{base} ({company_name})"
    return f"{base} — {item.step}"
