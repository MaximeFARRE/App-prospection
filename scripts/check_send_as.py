"""Vérifie les aliases Gmail (sendAs) configurés sur chaque compte.

Affiche la liste des adresses d'envoi autorisées pour chaque compte OAuth,
et indique si l'alias du compte 2 (GMAIL_EMAIL_2) est bien enregistré.

Usage :
    cd apps/api
    .venv\\Scripts\\python ..\\..\\scripts\\check_send_as.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.core.config import settings                        # noqa: E402
from google.auth.transport.requests import Request          # noqa: E402
from google.oauth2.credentials import Credentials           # noqa: E402
from googleapiclient.discovery import build                 # noqa: E402


_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def _build_service(account):
    creds = Credentials(
        token=None,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=account.client_id,
        client_secret=account.client_secret,
        scopes=_SCOPES,
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def check_account(index: int, account) -> None:
    print(f"\n  ── Compte {index} : {account.email} ──────────────────────────")

    if not account.is_configured:
        print("  ✗ Non configuré (champs manquants dans le .env)")
        return

    print("  Connexion...", end=" ", flush=True)
    try:
        service = _build_service(account)
        print("✓")
    except Exception as exc:
        print(f"\n  ✗ Erreur OAuth : {exc}")
        return

    # Profil du compte authentifié
    try:
        profile = service.users().getProfile(userId="me").execute()
        real_email = profile.get("emailAddress", "?")
        print(f"  Compte OAuth authentifié comme : {real_email}")
        if real_email.lower() != account.email.lower():
            print(f"  ⚠  Le token appartient à {real_email!r} "
                  f"(configuré comme {account.email!r})")
            print("     → L'envoi fonctionnera SI l'adresse configurée est un alias de ce compte.")
    except Exception as exc:
        print(f"  ⚠  Impossible de lire le profil : {exc}")

    # Liste des sendAs
    try:
        result = service.users().settings().sendAs().list(userId="me").execute()
        send_as_list = result.get("sendAs", [])
        print(f"\n  Adresses d'envoi autorisées ({len(send_as_list)}) :")
        for entry in send_as_list:
            addr      = entry.get("sendAsEmail", "?")
            is_default = entry.get("isDefault", False)
            verified   = entry.get("verificationStatus", "?")
            default_tag = " [DÉFAUT]" if is_default else ""
            verified_tag = " ✓" if verified == "accepted" else f" ⚠ ({verified})"
            print(f"    • {addr}{default_tag}{verified_tag}")

            # Vérification spécifique pour l'alias du compte 2
            if index == 2 and addr.lower() == account.email.lower():
                if verified == "accepted":
                    print(f"      → Alias {account.email!r} confirmé : l'envoi fonctionnera.")
                else:
                    print(f"      → Alias {account.email!r} NON vérifié — va dans Gmail ›")
                    print("         Paramètres › Voir tous les paramètres › Comptes")
                    print("         et clique sur « Vérifier » à côté de l'alias.")
    except Exception as exc:
        print(f"  ✗ Impossible de lister les sendAs : {exc}")
        print("    (Scope gmail.settings.basic manquant ? Relance gmail_setup.py)")


def main() -> None:
    print("\n  ── Vérification des aliases Gmail (sendAs) ─────────────────")
    accounts = settings.configured_gmail_accounts
    if not accounts:
        print("  ✗ Aucun compte Gmail configuré dans le .env")
        sys.exit(1)

    for i, account in enumerate(accounts, start=1):
        check_account(i, account)

    print("\n  ── Résumé ───────────────────────────────────────────────────")
    print("  Si l'alias configuré dans GMAIL_EMAIL_2 est listé et vérifié (✓),")
    print("  les mails seront bien envoyés depuis cette adresse.")
    print("  Si le token appartient au compte principal (GMAIL_EMAIL_1),")
    print("  c'est NORMAL : Gmail envoie via le compte principal au nom de l'alias.\n")


if __name__ == "__main__":
    main()
