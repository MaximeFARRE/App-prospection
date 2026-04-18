from __future__ import annotations

import argparse
import csv
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


@dataclass(frozen=True)
class GmailAccountCredentials:
    email: str
    client_id: str
    client_secret: str
    refresh_token: str


@dataclass
class SentContactStat:
    email: str
    sent_count: int = 0
    last_sent_at: datetime | None = None
    mailboxes: set[str] = field(default_factory=set)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect contacts already contacted from Gmail sent mails.",
    )
    parser.add_argument(
        "--output-csv",
        default="data/exports/gmail_sent_contacts.csv",
        help="CSV output path.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional JSON output path.",
    )
    parser.add_argument(
        "--max-messages-per-account",
        type=int,
        default=0,
        help="Optional hard limit per mailbox (0 = no limit).",
    )
    parser.add_argument(
        "--print-limit",
        type=int,
        default=20,
        help="Number of rows displayed in console summary.",
    )
    return parser.parse_args()


def load_dotenv_file(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values

    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        values[key.strip()] = raw_value.strip().strip('"').strip("'")
    return values


def read_env_value(key: str, fallback: dict[str, str]) -> str:
    direct_value = os.getenv(key)
    if direct_value:
        return direct_value.strip()
    return fallback.get(key, "").strip()


def load_gmail_accounts(project_root: Path) -> list[GmailAccountCredentials]:
    dotenv_values = load_dotenv_file(project_root / ".env")
    accounts: list[GmailAccountCredentials] = []
    for suffix in ("1", "2"):
        email = read_env_value(f"GMAIL_EMAIL_{suffix}", dotenv_values)
        client_id = read_env_value(f"GMAIL_CLIENT_ID_{suffix}", dotenv_values)
        client_secret = read_env_value(f"GMAIL_CLIENT_SECRET_{suffix}", dotenv_values)
        refresh_token = read_env_value(f"GMAIL_REFRESH_TOKEN_{suffix}", dotenv_values)

        if all((email, client_id, client_secret, refresh_token)):
            accounts.append(
                GmailAccountCredentials(
                    email=email,
                    client_id=client_id,
                    client_secret=client_secret,
                    refresh_token=refresh_token,
                )
            )
    return accounts


def normalize_email(value: str) -> str:
    return value.strip().lower()


def parse_message_date(raw_date: str) -> datetime | None:
    if not raw_date:
        return None
    try:
        parsed = parsedate_to_datetime(raw_date)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_recipients(headers: dict[str, str]) -> set[str]:
    recipients: set[str] = set()
    values = [headers.get("To", ""), headers.get("Cc", "")]
    for _display_name, address in getaddresses(values):
        normalized = normalize_email(address)
        if "@" not in normalized:
            continue
        recipients.add(normalized)
    return recipients


def build_gmail_client(account: GmailAccountCredentials) -> Any:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Missing Google dependencies. Install backend requirements first: "
            "pip install -r apps/api/requirements.txt"
        ) from error

    credentials = Credentials(
        token=None,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account.client_id,
        client_secret=account.client_secret,
        scopes=[GMAIL_READONLY_SCOPE],
    )
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def iter_sent_message_ids(gmail_service: Any, limit: int) -> list[str]:
    message_ids: list[str] = []
    page_token: str | None = None

    while True:
        response = (
            gmail_service.users()
            .messages()
            .list(
                userId="me",
                q="in:sent",
                maxResults=500,
                pageToken=page_token,
            )
            .execute()
        )

        for item in response.get("messages", []):
            message_id = item.get("id")
            if message_id:
                message_ids.append(message_id)
            if limit > 0 and len(message_ids) >= limit:
                return message_ids

        page_token = response.get("nextPageToken")
        if not page_token:
            return message_ids


def fetch_metadata_headers(gmail_service: Any, message_id: str) -> dict[str, str]:
    response = (
        gmail_service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["To", "Cc", "Date"],
        )
        .execute()
    )
    payload = response.get("payload", {})
    headers_list = payload.get("headers", [])

    headers: dict[str, str] = {}
    for item in headers_list:
        name = item.get("name")
        value = item.get("value")
        if name and value:
            headers[name] = value
    return headers


def collect_sent_contacts(
    accounts: list[GmailAccountCredentials],
    max_messages_per_account: int,
) -> list[SentContactStat]:
    stats_by_email: dict[str, SentContactStat] = {}
    owned_mailboxes = {normalize_email(account.email) for account in accounts}

    for account in accounts:
        service = build_gmail_client(account)
        message_ids = iter_sent_message_ids(service, max_messages_per_account)

        for message_id in message_ids:
            headers = fetch_metadata_headers(service, message_id)
            recipients = extract_recipients(headers)
            sent_at = parse_message_date(headers.get("Date", ""))

            for recipient in recipients:
                if recipient in owned_mailboxes:
                    continue

                current = stats_by_email.setdefault(recipient, SentContactStat(email=recipient))
                current.sent_count += 1
                current.mailboxes.add(normalize_email(account.email))
                if sent_at and (current.last_sent_at is None or sent_at > current.last_sent_at):
                    current.last_sent_at = sent_at

    return sorted(
        stats_by_email.values(),
        key=lambda item: (-item.sent_count, item.email),
    )


def to_serializable_rows(stats: list[SentContactStat]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in stats:
        rows.append(
            {
                "email": item.email,
                "last_sent_at": item.last_sent_at.isoformat() if item.last_sent_at else "",
                "sent_count": item.sent_count,
                "mailboxes": ",".join(sorted(item.mailboxes)),
            }
        )
    return rows


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file_handle:
        writer = csv.DictWriter(
            file_handle,
            fieldnames=["email", "last_sent_at", "sent_count", "mailboxes"],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(rows, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def print_summary(rows: list[dict[str, Any]], print_limit: int) -> None:
    print(f"Total unique contacted emails: {len(rows)}")
    for index, row in enumerate(rows[:print_limit], start=1):
        print(
            f"{index:>3}. {row['email']} | sent_count={row['sent_count']} | "
            f"last_sent_at={row['last_sent_at']} | mailboxes={row['mailboxes']}"
        )


def main() -> int:
    args = parse_arguments()
    project_root = Path(__file__).resolve().parents[1]
    accounts = load_gmail_accounts(project_root)

    if not accounts:
        print("No Gmail account credentials found in environment variables or .env file.")
        print("Expected keys: GMAIL_EMAIL_1/2, GMAIL_CLIENT_ID_1/2, GMAIL_CLIENT_SECRET_1/2, GMAIL_REFRESH_TOKEN_1/2")
        return 1

    stats = collect_sent_contacts(accounts, args.max_messages_per_account)
    rows = to_serializable_rows(stats)

    csv_path = project_root / args.output_csv
    write_csv(rows, csv_path)
    print(f"CSV exported to: {csv_path}")

    if args.output_json:
        json_path = project_root / args.output_json
        write_json(rows, json_path)
        print(f"JSON exported to: {json_path}")

    print_summary(rows, args.print_limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
