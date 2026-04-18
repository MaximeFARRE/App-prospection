"""Script d'autorisation OAuth2 Gmail.

Lance ce script une fois par boîte mail pour obtenir les refresh_token
à copier dans le fichier .env.

Usage :
    cd apps/api
    .venv\\Scripts\\python ..\\..\\scripts\\gmail_setup.py

Le script ouvre le navigateur, te demande de te connecter à Google,
puis affiche le refresh_token à copier dans .env.
"""
import json
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

# Ajoute apps/api au path pour importer les dépendances installées dans le venv
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from google_auth_oauthlib.flow import Flow  # noqa: E402

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
REDIRECT_URI = "http://localhost:8080"


def main() -> None:
    print("\n  Configuration OAuth2 Gmail")
    print("  " + "─" * 40)
    print()
    print("  Colle les valeurs trouvées dans Google Cloud Console")
    print("  (APIs & Services → Credentials → ton OAuth 2.0 Client ID)")
    print()

    client_id = input("  Client ID     : ").strip()
    client_secret = input("  Client Secret : ").strip()
    account_label = input("  Compte (1 ou 2 pour identifier dans .env) : ").strip()

    if not client_id or not client_secret:
        print("\n  ERREUR : client_id et client_secret sont obligatoires.")
        sys.exit(1)

    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",        # force le renvoi du refresh_token
        include_granted_scopes="true",
    )

    print()
    print("  Ouverture du navigateur pour l'autorisation Google...")
    print(f"  URL : {auth_url}")
    print()
    webbrowser.open(auth_url)

    # Serveur local temporaire pour capturer le code de retour
    auth_code = _wait_for_callback()
    if not auth_code:
        print("\n  ERREUR : aucun code reçu.")
        sys.exit(1)

    flow.fetch_token(code=auth_code)
    credentials = flow.credentials

    print()
    print("  ✓ Autorisation réussie !")
    print()
    print(f"  Copie ces lignes dans ton fichier .env :")
    print()
    print(f"  GMAIL_CLIENT_ID_{account_label}={client_id}")
    print(f"  GMAIL_CLIENT_SECRET_{account_label}={client_secret}")
    print(f"  GMAIL_REFRESH_TOKEN_{account_label}={credentials.refresh_token}")
    print()


def _wait_for_callback() -> str | None:
    """Lance un mini serveur HTTP local pour récupérer le code OAuth2."""
    received_code: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            params = parse_qs(urlparse(self.path).query)
            code = params.get("code", [None])[0]
            if code:
                received_code.append(code)
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>Autorisation re\xc3\xa7ue. Tu peux fermer cet onglet.</h2>"
            )

        def log_message(self, *args) -> None:
            pass  # silence les logs HTTP

    server = HTTPServer(("localhost", 8080), Handler)
    server.handle_request()
    return received_code[0] if received_code else None


if __name__ == "__main__":
    main()
