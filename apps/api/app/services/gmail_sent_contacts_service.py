"""Service de récupération des contacts déjà contactés via Gmail.

Pour chaque boîte configurée, parcourt tous les mails envoyés (in:sent),
extrait les destinataires et croise avec la base de contacts.
Les contacts trouvés reçoivent une entrée Message(type="historical")
qui sera utilisée par eligibility_service pour les exclure des campagnes.

Usage :
    from app.db.session import SessionLocal
    from app.services.gmail_sent_contacts_service import sync_sent_contacts

    db = SessionLocal()
    results = sync_sent_contacts(db)
    db.close()
"""
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import getaddresses, parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.core.config import GmailAccount, settings
from app.models.contact import Contact
from app.models.message import Message
from app.utils.email_normalization import normalize_email


GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


# ── Résultats ─────────────────────────────────────────────────────────────────

@dataclass
class AccountSyncResult:
    account_email: str
    messages_scanned: int = 0
    contacts_matched: int = 0
    already_recorded: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def new_entries(self) -> int:
        return self.contacts_matched - self.already_recorded


@dataclass
class SyncResult:
    accounts: list[AccountSyncResult] = field(default_factory=list)

    @property
    def total_new_entries(self) -> int:
        return sum(a.new_entries for a in self.accounts)

    @property
    def total_contacts_matched(self) -> int:
        return sum(a.contacts_matched for a in self.accounts)


# ── Point d'entrée public ─────────────────────────────────────────────────────

def sync_sent_contacts(
    db: Session,
    since_days: int | None = None,
) -> SyncResult:
    """Scanne les boîtes Gmail configurées et marque les contacts déjà contactés.

    Args:
        db:         Session SQLAlchemy active.
        since_days: Si fourni, ne scanne que les mails des N derniers jours.
                    None = tout l'historique (plus lent).

    Returns:
        SyncResult avec le détail par compte.
    """
    result = SyncResult()

    accounts = settings.configured_gmail_accounts
    if not accounts:
        raise RuntimeError(
            "Aucun compte Gmail configuré. "
            "Lance scripts/gmail_setup.py pour obtenir les tokens OAuth2."
        )

    for account in accounts:
        account_result = _sync_account(account, db, since_days)
        result.accounts.append(account_result)

    db.commit()
    return result


# ── Sync d'un compte ──────────────────────────────────────────────────────────

def _sync_account(
    account: GmailAccount,
    db: Session,
    since_days: int | None,
) -> AccountSyncResult:
    result = AccountSyncResult(account_email=account.email)

    try:
        service = _build_service(account)
        message_ids = _list_sent_message_ids(service, since_days)
        result.messages_scanned = len(message_ids)

        for msg_id in message_ids:
            try:
                _process_message(msg_id, service, account.email, db, result)
            except HttpError as e:
                result.errors.append(f"Message {msg_id} : {e}")
            except Exception as e:
                result.errors.append(f"Message {msg_id} : {e}")

    except Exception as e:
        result.errors.append(f"Erreur compte {account.email} : {e}")

    return result


# ── Traitement d'un message ───────────────────────────────────────────────────

def _process_message(
    msg_id: str,
    service,
    from_email: str,
    db: Session,
    result: AccountSyncResult,
) -> None:
    headers = _get_message_headers(service, msg_id)
    sent_at = _parse_gmail_date(headers.get("Date"))
    recipient_emails = _extract_recipient_emails(headers)

    for raw_email in recipient_emails:
        normalized = normalize_email(raw_email)
        if not normalized:
            continue

        contact = db.query(Contact).filter_by(email_normalized=normalized).first()
        if not contact:
            continue  # email pas dans notre base, on ignore

        result.contacts_matched += 1

        # Éviter les doublons dans messages
        already = db.query(Message).filter_by(
            contact_id=contact.id,
            gmail_message_id=msg_id,
        ).first()
        if already:
            result.already_recorded += 1
            continue

        db.add(Message(
            contact_id=contact.id,
            campaign_name=None,
            subject="",   # non récupéré pour les historiques (économise des appels API)
            body="",
            from_email=from_email,
            message_type="historical",
            gmail_message_id=msg_id,
            sent_at=sent_at,
        ))


# ── Gmail API ─────────────────────────────────────────────────────────────────

def _build_service(account: GmailAccount):
    """Construit le client Gmail à partir du refresh_token stocké en config."""
    creds = Credentials(
        token=None,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account.client_id,
        client_secret=account.client_secret,
        scopes=GMAIL_SCOPES,
    )
    creds.refresh(Request())  # échange le refresh_token contre un access_token frais
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _list_sent_message_ids(service, since_days: int | None) -> list[str]:
    """Retourne la liste de tous les IDs de messages envoyés."""
    query = "in:sent"
    if since_days is not None:
        after_date = (datetime.now() - timedelta(days=since_days)).strftime("%Y/%m/%d")
        query += f" after:{after_date}"

    ids: list[str] = []
    page_token = None

    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": 500}
        if page_token:
            kwargs["pageToken"] = page_token

        resp = service.users().messages().list(**kwargs).execute()

        for msg in resp.get("messages", []):
            ids.append(msg["id"])

        page_token = resp.get("nextPageToken")
        if not page_token:
            break

        time.sleep(0.1)  # respect du quota Gmail API

    return ids


def _get_message_headers(service, msg_id: str) -> dict[str, str]:
    """Récupère uniquement les headers To, Cc et Date (évite de charger le body)."""
    resp = service.users().messages().get(
        userId="me",
        id=msg_id,
        format="metadata",
        metadataHeaders=["To", "Cc", "Date"],
    ).execute()

    headers: dict[str, str] = {}
    for h in resp.get("payload", {}).get("headers", []):
        headers[h["name"]] = h["value"]
    return headers


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_recipient_emails(headers: dict[str, str]) -> list[str]:
    """Extrait les adresses email depuis les champs To et Cc.

    Gère les formats : "Prénom Nom <email>" et "email" simples.
    """
    raw = f"{headers.get('To', '')},{headers.get('Cc', '')}".strip(",")
    if not raw:
        return []
    addresses = getaddresses([raw])
    return [addr.strip() for _, addr in addresses if addr.strip()]


def _parse_gmail_date(date_str: str | None) -> datetime:
    """Convertit un header Date RFC 2822 en datetime naïf UTC."""
    if not date_str:
        return datetime.utcnow()
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()
