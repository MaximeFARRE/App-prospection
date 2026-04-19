from __future__ import annotations

import base64
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.core.config import GmailAccount, settings
from app.models.contact import Contact
from app.models.message import Message
from app.services.reply_classification_service import ReplyCandidate, record_classified_reply
from app.utils.email_normalization import normalize_email

READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass(slots=True)
class AccountReplySyncResult:
    account_email: str
    threads_scanned: int = 0
    inbound_messages_scanned: int = 0
    contacts_matched: int = 0
    replies_created: int = 0
    replies_existing: int = 0
    campaign_states_updated: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReplySyncResult:
    accounts: list[AccountReplySyncResult] = field(default_factory=list)

    @property
    def total_replies_created(self) -> int:
        return sum(account.replies_created for account in self.accounts)

    @property
    def total_campaign_states_updated(self) -> int:
        return sum(account.campaign_states_updated for account in self.accounts)


def sync_incoming_replies(db: Session, since_days: int | None = 30) -> ReplySyncResult:
    accounts = settings.configured_gmail_accounts
    if not accounts:
        raise RuntimeError("Aucun compte Gmail configure pour synchroniser les reponses.")

    contacts_by_email = _load_contacts_by_email(db)
    result = ReplySyncResult()

    for account in accounts:
        account_result = _sync_account_replies(
            account=account,
            db=db,
            contacts_by_email=contacts_by_email,
            since_days=since_days,
        )
        result.accounts.append(account_result)

    db.commit()
    return result


def sync_replies(db: Session, since_days: int | None = 30) -> ReplySyncResult:
    return sync_incoming_replies(db=db, since_days=since_days)


def _sync_account_replies(
    account: GmailAccount,
    db: Session,
    contacts_by_email: dict[str, Contact],
    since_days: int | None,
) -> AccountReplySyncResult:
    result = AccountReplySyncResult(account_email=account.email)

    try:
        service = _build_readonly_service(account)
        thread_ids = _list_thread_ids(service=service, since_days=since_days)
        result.threads_scanned = len(thread_ids)

        for thread_id in thread_ids:
            try:
                _process_thread_replies(
                    thread_id=thread_id,
                    service=service,
                    db=db,
                    contacts_by_email=contacts_by_email,
                    result=result,
                )
            except HttpError as exc:
                result.errors.append(f"Thread {thread_id}: {exc}")
            except Exception as exc:
                result.errors.append(f"Thread {thread_id}: {exc}")
            time.sleep(0.05)

    except Exception as exc:
        result.errors.append(f"Compte {account.email}: {exc}")

    return result

def _process_thread_replies(
    thread_id: str,
    service: Any,
    db: Session,
    contacts_by_email: dict[str, Contact],
    result: AccountReplySyncResult,
) -> None:
    thread = service.users().threads().get(userId="me", id=thread_id, format="full").execute()
    thread_messages = list(thread.get("messages", []))
    local_message = _resolve_local_message_for_thread(thread_messages=thread_messages, db=db)

    for message in thread_messages:
        if "SENT" in message.get("labelIds", []):
            continue

        try:
            result.inbound_messages_scanned += 1
            headers = _get_headers(message)
            sender = normalize_email(_extract_email_address(headers.get("From")))
            if sender is None:
                continue

            contact = contacts_by_email.get(sender)
            if contact is None:
                continue

            result.contacts_matched += 1
            body = _extract_message_text(message)
            candidate = ReplyCandidate(
                contact_id=contact.id,
                in_reply_to_message_id=local_message.id if local_message is not None else None,
                subject=_clean_optional(headers.get("Subject")),
                body=body,
                from_email=sender,
                gmail_thread_id=_clean_optional(thread.get("id")),
                received_at=_resolve_received_at(message, headers.get("Date")),
                campaign_name=local_message.campaign_name if local_message is not None else None,
            )
            with db.begin_nested():
                persist_result = record_classified_reply(candidate, db)
            if persist_result.created:
                result.replies_created += 1
            else:
                result.replies_existing += 1
            result.campaign_states_updated += persist_result.updated_campaign_states
        except Exception as exc:
            message_id = _clean_optional(message.get("id")) or "unknown"
            result.errors.append(f"Thread {thread_id} message {message_id}: {exc}")

def _load_contacts_by_email(db: Session) -> dict[str, Contact]:
    contacts = (
        db.query(Contact)
        .filter(Contact.email_normalized.is_not(None))
        .all()
    )
    by_email: dict[str, Contact] = {}
    for contact in contacts:
        normalized_email = normalize_email(contact.email_normalized)
        if normalized_email is not None:
            by_email[normalized_email] = contact
    return by_email

def _resolve_local_message_for_thread(thread_messages: list[dict[str, Any]], db: Session) -> Message | None:
    sent_ids = [
        str(message.get("id"))
        for message in thread_messages
        if "SENT" in message.get("labelIds", []) and message.get("id")
    ]
    if not sent_ids:
        return None

    rows = db.query(Message).filter(Message.gmail_message_id.in_(sent_ids)).all()
    if not rows:
        return None

    rows.sort(key=lambda row: (row.sent_at, row.id), reverse=True)
    return rows[0]

def _build_readonly_service(account: GmailAccount) -> Any:
    creds = Credentials(
        token=None,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account.client_id,
        client_secret=account.client_secret,
        scopes=READONLY_SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def _list_thread_ids(service: Any, since_days: int | None) -> list[str]:
    query = "in:inbox -from:me"
    if since_days is not None and since_days > 0:
        after_date = (datetime.utcnow() - timedelta(days=since_days)).strftime("%Y/%m/%d")
        query = f"{query} after:{after_date}"

    thread_ids: list[str] = []
    next_page_token: str | None = None

    while True:
        params: dict[str, Any] = {"userId": "me", "q": query, "maxResults": 100}
        if next_page_token:
            params["pageToken"] = next_page_token

        response = service.users().threads().list(**params).execute()
        for item in response.get("threads", []):
            thread_id = _clean_optional(item.get("id"))
            if thread_id is not None:
                thread_ids.append(thread_id)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return thread_ids

def _get_headers(message: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in message.get("payload", {}).get("headers", []):
        name = str(header.get("name", ""))
        value = str(header.get("value", ""))
        if name:
            headers[name] = value
    return headers

def _extract_email_address(value: str | None) -> str | None:
    _, address = parseaddr(str(value or ""))
    cleaned = address.strip()
    return cleaned or None

def _extract_message_text(message: dict[str, Any]) -> str:
    payload = message.get("payload", {})
    plain_parts = _collect_payload_parts(payload, "text/plain")
    if plain_parts:
        return "\n".join(part for part in plain_parts if part).strip()

    html_parts = _collect_payload_parts(payload, "text/html")
    if html_parts:
        html = "\n".join(part for part in html_parts if part)
        return _html_to_text(html)

    return str(message.get("snippet", "")).strip()

def _collect_payload_parts(payload: dict[str, Any], mime_type: str) -> list[str]:
    collected: list[str] = []
    if payload.get("mimeType") == mime_type:
        decoded = _decode_body_data(payload.get("body", {}).get("data"))
        if decoded:
            collected.append(decoded)

    for part in payload.get("parts", []) or []:
        collected.extend(_collect_payload_parts(part, mime_type))

    return collected

def _decode_body_data(data: str | None) -> str:
    if not data:
        return ""
    try:
        padding = "=" * (-len(data) % 4)
        raw_bytes = base64.urlsafe_b64decode(data + padding)
        return raw_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _html_to_text(content: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", content)
    normalized = re.sub(r"\s+", " ", no_tags)
    return normalized.strip()

def _resolve_received_at(message: dict[str, Any], date_header: str | None) -> datetime:
    internal_date = message.get("internalDate")
    try:
        if internal_date:
            timestamp = int(str(internal_date)) / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)

        if date_header:
            parsed = parsedate_to_datetime(date_header)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=None)
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()

    return datetime.utcnow()

def _clean_optional(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned if cleaned else None
