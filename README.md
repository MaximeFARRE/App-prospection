# Prospection CRM

A personal-use desktop CRM for job prospecting via email campaigns. Manages contacts, sends personalized outreach emails through the Gmail API, tracks replies, and handles follow-ups — all from a local SQLite database with no external SaaS dependency.

Built for people who want to run a structured, multi-account email prospecting campaign with full control over their data.

---

## Features

- **Contact management** — import from CSV, deduplicate, block contacts, view full history
- **Email campaigns** — prepare and send intro + follow-up sequences with A/B template rotation
- **Multi-account Gmail** — distribute sends across up to 3 Gmail accounts with configurable weights
- **Email verification** — optional [QuickEmailVerification](https://quickemailverification.com/) integration to skip invalid addresses
- **Reply tracking** — sync replies from Gmail, classify as positive / negative / neutral
- **Rate limiting** — per-account daily/hourly limits, per-company weekly caps, randomized delays
- **CV attachment** — optionally attach a PDF to every outreach email
- **Bilingual templates** — language auto-detected per contact (French / English)

---

## Architecture

```
apps/
├── api/              FastAPI backend + SQLAlchemy (SQLite)
│   ├── app/
│   │   ├── api/          HTTP routes (thin — validation + service call only)
│   │   ├── core/         Settings loaded from .env via pydantic-settings
│   │   ├── models/       SQLAlchemy ORM models
│   │   ├── repositories/ Database query layer
│   │   ├── schemas/      Pydantic request/response schemas
│   │   └── services/     Business logic
│   ├── alembic/          Database migrations
│   └── tests/
└── desktop/          PyQt6 GUI — talks to the API over localhost
    ├── views/        Full-screen views (contacts, campaigns, replies, settings…)
    ├── widgets/      Dialogs and reusable components
    └── workers/      QThread workers for non-blocking API calls

data/
├── templates/    Markdown email templates (see Template Format below)
├── imports/      CSV files to import — gitignored
├── exports/      Output CSVs — gitignored
└── secure/       Plain-text API key files — gitignored

scripts/          Utility scripts (Gmail OAuth setup, alias check, test send…)
docs/             Architecture notes and API contract
```

---

## Prerequisites

- **Python 3.11+**
- A **Google Cloud project** with the Gmail API enabled and an OAuth 2.0 Desktop client (see [Gmail OAuth Setup](#gmail-oauth-setup))
- *(Optional)* A [QuickEmailVerification](https://quickemailverification.com/) API key for email address validation

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/MaximeFARRE/App-prospection.git
cd App-prospection

# 2. Create and activate a virtual environment
cd apps/api
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Configure your environment
cp ../../.env.example ../../.env
# Edit .env — fill in Gmail credentials, SENDER_NAME, and optional API keys

# 5. Run database migrations
alembic upgrade head

# 6. Start the backend API
python -m uvicorn app.main:app --reload

# 7. In a second terminal, start the desktop GUI
cd ../desktop
python main.py
```

> The desktop app connects to `http://localhost:8000` by default. Keep both processes running.

---

## Gmail OAuth Setup

The app uses the Gmail API (OAuth 2.0) instead of SMTP so it can read replies as well as send emails.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a new project (or use an existing one).
2. Enable the **Gmail API**: *APIs & Services → Library → Gmail API → Enable*.
3. Create OAuth credentials: *APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID*.
   - Application type: **Desktop app**
   - Download the JSON file and save it as `credentials.json` in the repo root (already gitignored).
4. Run the setup script for each Gmail account you want to use:
   ```bash
   cd apps/api
   .venv\Scripts\python ..\..\scripts\gmail_setup.py
   ```
   The script opens a browser for OAuth consent. After authorization it prints the `client_id`, `client_secret`, and `refresh_token` — copy them into `.env`:
   ```
   GMAIL_CLIENT_ID_1=...
   GMAIL_CLIENT_SECRET_1=...
   GMAIL_REFRESH_TOKEN_1=...
   GMAIL_EMAIL_1=your.account@gmail.com
   ```
5. Repeat for up to 3 accounts (`_1`, `_2`, `_3`). Accounts without all four fields are silently ignored.

---

## Template Format

Templates live in `data/templates/`. Each file is a Markdown file with a `Subject:` line on the first line:

```
Subject: Your subject line here

Body text with {{variables}} substituted at send time.
```

**Naming convention:** `{step}_{lang}_{variant}.md`

| Part | Values | Meaning |
|------|--------|---------|
| `step` | `intro`, `followup_1`, `followup_2` | Position in the sequence |
| `lang` | `fr`, `en` | Language — auto-detected from the contact's country |
| `variant` | `a`, `b`, … | A/B variant — rotated across sends |

**Available variables:**

| Variable | Description |
|----------|-------------|
| `{{civilite}}` | Honorific — `M.` or `Mme` based on detected gender |
| `{{first_name}}` | Contact's first name |
| `{{last_name}}` | Contact's last name |
| `{{company}}` | Company name |
| `{{sender_name}}` | Your name (from `SENDER_NAME` in `.env`) |
| `{{sender_email}}` | The Gmail account address used for this send |
| `{{sender_website}}` | Your website URL — add `SENDER_WEBSITE=...` to `.env` if needed |

The follow-up templates are rendered in the context of the original intro thread, so recipients see a proper reply chain.

---

## Importing Contacts

Place a CSV file in `data/imports/` and use the **Imports** tab in the GUI.

The importer uses flexible column matching — these headers are recognized:

```
first_name  /  prospect_first_name
last_name   /  prospect_last_name
email       /  contact_professions_email
company     /  prospect_company_name
position    /  prospect_job_title
country     /  prospect_country_name
linkedin    /  linkedin_url
sex         /  gender
```

Duplicate detection (by normalized email, then by name + company) runs automatically on import.

---

## Running a Campaign

1. Import contacts via the **Imports** tab.
2. Go to the **Campaigns** tab, enter a campaign name, and click **Prepare**.
3. Review the preparation summary: contact count, language split, account distribution, estimated send duration.
4. Click **Start** to begin sending. A real-time progress view shows each send.
5. After sending, use **Sync Replies** in the **Replies** tab to pull new Gmail replies and auto-classify them.

Contacts who have already replied, been blocked, or were contacted in a previous campaign are automatically excluded.

---

## Configuration Reference

All settings live in `.env` (copy from `.env.example`).

| Variable | Default | Description |
|----------|---------|-------------|
| `GMAIL_EMAIL_N` | — | Email address for account N (N = 1, 2, 3) |
| `GMAIL_CLIENT_ID_N` | — | OAuth client ID |
| `GMAIL_CLIENT_SECRET_N` | — | OAuth client secret |
| `GMAIL_REFRESH_TOKEN_N` | — | OAuth refresh token |
| `GMAIL_WEIGHT_N` | `50` | Relative send weight for account N |
| `SENDER_NAME` | — | Your name as it appears in the From field |
| `CV_PATH` | `data/cv.pdf` | Path to a PDF file to attach (leave blank to disable) |
| `DAILY_SEND_LIMIT_PER_ACCOUNT` | `30` | Max emails per account per day |
| `HOURLY_SEND_LIMIT_PER_ACCOUNT` | `5` | Max emails per account per hour |
| `MIN_DELAY_BETWEEN_SENDS_SEC` | `60` | Min seconds between consecutive sends |
| `MAX_DELAY_BETWEEN_SENDS_SEC` | `180` | Max seconds between consecutive sends |
| `COMPANY_WEEKLY_SEND_LIMIT` | `4` | Max contacts from the same company per week |
| `QUICKEMAILVERIFICATION_API_KEY` | — | API key for email validation (optional) |
| `EMAIL_VERIFICATION_TTL_DAYS` | `30` | Days before re-verifying an email address |

---

## Contributing

This is personal-use software shared as a reference implementation. Contributions are welcome if they align with the architecture:

- Services in `apps/api/app/services/` — business logic lives here.
- Thin routes in `apps/api/app/api/` — routes only validate input and call a service.
- No direct DB access from the desktop app — all reads/writes go through the API.
- Run the test suite before opening a PR:
  ```bash
  cd apps/api
  pytest
  ```

---

## License

MIT — see [`LICENSE`](LICENSE).
