"""Script de test d'envoi — vérifie que tout le pipeline fonctionne.

Envoie un vrai mail à chaque adresse de test en utilisant le même code
que la campagne (render, CV en PJ, compte Gmail configuré).

Usage :
    cd apps/api
    .venv\\Scripts\\python ..\\..\\scripts\\test_send.py
    .venv\\Scripts\\python ..\\..\\scripts\\test_send.py --dry-run   # aperçu sans envoyer
"""
from __future__ import annotations

import argparse
import base64
import sys
from dataclasses import dataclass
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── Chemin vers apps/api ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import GmailAccount, settings  # noqa: E402
from app.models.company import Company               # noqa: E402
from app.models.contact import Contact               # noqa: E402
from app.services.mail_render_service import render_for_contact  # noqa: E402
from google.auth.transport.requests import Request   # noqa: E402
from google.oauth2.credentials import Credentials    # noqa: E402
from googleapiclient.discovery import build          # noqa: E402


# ── Contacts de test ──────────────────────────────────────────────────────────
# (first_name, last_name, email, country, sex, company_name, contact_id)
TEST_TARGETS = [
    ("Maxime",  "Farré",  "maximefarre54@gmail.com",   "france", "homme", "Test FR",     1),
    ("Maxime",  "Farré",  "maxime.farre@occifloc.fr",  "france", "homme", "Occifloc FR", 2),
    ("Maxime",  "Farré",  "occifloc@gmail.com",        "canada", "homme", "Occifloc EN", 3),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_contact(
    contact_id: int,
    first_name: str,
    last_name: str,
    email: str,
    country: str,
    sex: str,
    company_name: str,
) -> Contact:
    c = Contact(
        first_name=first_name,
        last_name=last_name,
        email=email,
        email_normalized=email.lower(),
        country=country,
        sex=sex,
    )
    c.id = contact_id
    setattr(c, "company", Company(name=company_name))
    return c


def _build_service(account: GmailAccount):
    creds = Credentials(
        token=None,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account.client_id,
        client_secret=account.client_secret,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _build_mime(to_email: str, from_email: str, subject: str, body_html: str) -> dict:
    msg = MIMEMultipart("mixed")
    msg["To"]      = to_email
    msg["From"]    = from_email
    msg["Subject"] = subject

    body_part = MIMEMultipart("alternative")
    plain = body_html.replace("<p>", "").replace("</p>", "\n").replace("<br>", "\n")
    body_part.attach(MIMEText(plain, "plain", "utf-8"))
    body_part.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(body_part)

    cv_path = Path(settings.cv_path)
    if cv_path.is_file():
        cv_bytes = cv_path.read_bytes()
        attachment = MIMEApplication(cv_bytes, _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=cv_path.name)
        msg.attach(attachment)
        print(f"    📎 CV joint : {cv_path.name} ({cv_path.stat().st_size // 1024} Ko)")
    else:
        print(f"    ⚠  CV introuvable : {cv_path} — envoi sans pièce jointe")

    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")}


# ── Programme principal ───────────────────────────────────────────────────────

def run(dry_run: bool) -> None:
    print("\n  ── Test d'envoi Gmail ─────────────────────────────")
    print(f"  Mode : {'DRY RUN (aucun mail envoyé)' if dry_run else 'ENVOI RÉEL'}\n")

    # Vérification du compte Gmail
    accounts = settings.configured_gmail_accounts
    if not accounts:
        print("  ✗ ERREUR : Aucun compte Gmail configuré dans le .env")
        print("    Vérifiez GMAIL_CLIENT_ID_1, GMAIL_CLIENT_SECRET_1, GMAIL_REFRESH_TOKEN_1")
        sys.exit(1)

    account = accounts[0]
    print(f"  Compte expéditeur : {account.email}")
    print(f"  Nombre de comptes configurés : {len(accounts)}\n")

    # Connexion Gmail (seulement si envoi réel)
    service = None
    if not dry_run:
        print("  Connexion à l'API Gmail...", end=" ", flush=True)
        try:
            service = _build_service(account)
            print("✓\n")
        except Exception as exc:
            print(f"\n  ✗ ERREUR de connexion : {exc}")
            sys.exit(1)

    # Envoi des mails de test
    results: list[tuple[str, bool, str]] = []

    for i, (first_name, last_name, email, country, sex, company_name, cid) in enumerate(TEST_TARGETS):
        print(f"  [{i+1}/{len(TEST_TARGETS)}] {email}")

        contact = _make_contact(cid, first_name, last_name, email, country, sex, company_name)

        # Rendu du template (position=i pour tester la rotation)
        try:
            result = render_for_contact("intro", contact, account, position=i)
        except Exception as exc:
            print(f"    ✗ Erreur de rendu : {exc}")
            results.append((email, False, str(exc)))
            continue

        print(f"    Langue   : {result.language.upper()}  |  Variant : {result.ab_variant}")
        print(f"    Objet    : {result.subject}")
        # Aperçu du corps (50 premiers caractères du texte brut)
        body_preview = result.body.replace("<p>", "").replace("</p>", " ")[:100].strip()
        print(f"    Corps    : {body_preview}…")

        if dry_run:
            print("    → [DRY RUN] Non envoyé\n")
            results.append((email, True, "dry-run"))
            continue

        # Envoi réel
        try:
            payload = _build_mime(email, account.email, result.subject, result.body)
            response = service.users().messages().send(userId="me", body=payload).execute()
            gmail_id = response.get("id", "?")
            print(f"    ✓ Envoyé — Gmail ID : {gmail_id}\n")
            results.append((email, True, gmail_id))
        except Exception as exc:
            print(f"    ✗ Échec d'envoi : {exc}\n")
            results.append((email, False, str(exc)))

    # Résumé
    print("  ── Résumé ─────────────────────────────────────────")
    ok = sum(1 for _, success, _ in results if success)
    print(f"  {ok}/{len(results)} mails {'simulés' if dry_run else 'envoyés'} avec succès\n")
    for email, success, detail in results:
        icon = "✓" if success else "✗"
        print(f"  {icon} {email:<35} {detail}")
    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test d'envoi de mails via le pipeline campagne.")
    parser.add_argument("--dry-run", action="store_true", help="Aperçu sans envoi réel.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(dry_run=args.dry_run)
