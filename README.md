# Prospection CRM

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/PyQt6-6.7%2B-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="PyQt6">
  <img src="https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLite-embedded-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Gmail_API-OAuth2-EA4335?style=for-the-badge&logo=gmail&logoColor=white" alt="Gmail API">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/License-MIT-F7C948?style=for-the-badge" alt="MIT License">
</p>

<p align="center">
  Desktop CRM for structured email prospecting — multi-account Gmail, bilingual templates, reply tracking, A/B testing, and zero external dependencies.
</p>

---

## Overview

Prospection CRM is a self-contained Windows desktop application for running personalised outreach email campaigns. All data stays local in an embedded SQLite database. There is no subscription, no cloud sync, and no SaaS.

**Who it is for:** anyone who wants to run a structured cold-email campaign with full control over timing, wording, and delivery across multiple Gmail accounts.

---

## Features

| Category | What it does |
|---|---|
| **Contact management** | Import from CSV, deduplicate on normalised email, block/unblock, view full send history |
| **Email campaigns** | Prepare and send intro + follow-up sequences with per-contact eligibility checks |
| **Multi-account Gmail** | Distribute sends across up to 3 Gmail accounts with configurable weights |
| **A/B template testing** | Multiple variants per step rotated across sends; results visible in the dashboard |
| **Reply tracking** | Sync replies from Gmail, auto-classify as positive / negative / neutral |
| **Email verification** | Optional [QuickEmailVerification](https://quickemailverification.com/) integration skips invalid addresses before sending |
| **Rate limiting** | Per-account daily & hourly caps, per-company weekly limits, randomised delays between sends |
| **Bilingual templates** | Language auto-detected per contact (French / English) |
| **CV attachment** | Optionally attach a PDF to every outreach email |

---

## Architecture

The application is **100 % Python**. The desktop GUI imports the business-logic services directly — no HTTP is involved for normal use.

```
apps/
├── api/                    Python services + SQLAlchemy models (shared with desktop)
│   ├── app/
│   │   ├── api/            FastAPI routes (optional — for external integrations only)
│   │   ├── core/           pydantic-settings config loaded from .env
│   │   ├── db/             SQLAlchemy session + declarative base
│   │   ├── models/         ORM table definitions
│   │   ├── repositories/   SQL query layer
│   │   ├── schemas/        Pydantic request/response models
│   │   └── services/       All business logic
│   ├── alembic/            Database migrations (for the FastAPI server mode)
│   └── tests/
└── desktop/                PyQt6 GUI — imports api/app/* directly
    ├── views/              Full-screen views (contacts, campaigns, replies…)
    ├── widgets/            Dialogs and reusable components
    └── workers/            QThread workers for non-blocking operations

data/
├── templates/              Markdown email templates
├── imports/                CSV files to import (gitignored)
├── exports/                Output CSVs (gitignored)
├── secure/                 Plain-text API key files (gitignored)
└── app.db                  SQLite database — auto-created on first launch

scripts/
├── dev-start.ps1           Main launcher (called by Lancer l'app.bat)
├── gmail_setup.py          OAuth setup wizard for each Gmail account
└── …                       Utility scripts
```

**Dependency flow:**

```
desktop/views  →  desktop/workers  →  api/app/services  →  api/app/repositories  →  SQLite
```

One shared virtual environment: `apps/api/.venv`.

---

## Quick Start

### Prerequisites

- **Python 3.11 or later** — download at [python.org](https://www.python.org/downloads/). During installation, check **"Add Python to PATH"**.
- A **Google Cloud project** with the Gmail API enabled and at least one OAuth 2.0 Desktop client (see [Gmail OAuth Setup](#gmail-oauth-setup) below).

### Installation

```powershell
# 1. Clone the repository
git clone https://github.com/MaximeFARRE/App-prospection.git
cd App-prospection

# 2. Copy the environment template
copy .env.example .env
# Open .env and fill in your Gmail credentials and SENDER_NAME before the next step.
```

### Launch

Double-click **`Lancer l'app.bat`**.

On the first run the launcher will:
1. Create the Python virtual environment automatically (`apps/api/.venv`).
2. Install all dependencies from `requirements.txt`.
3. Create `data/imports/` and `data/exports/` if they do not exist.
4. Start the desktop application (the SQLite database is created automatically).

> If `.env` is missing, the launcher copies `.env.example` to `.env` and shows the path to edit before proceeding.

---

## Gmail OAuth Setup

The app uses Gmail OAuth 2.0 instead of SMTP so it can read replies as well as send emails.

**Step 1 — Create a Google Cloud project**

1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API**: *APIs & Services → Library → Gmail API → Enable*.
3. Create credentials: *APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID*.
   - Application type: **Desktop app**
   - Download the JSON and save it as `credentials.json` in the repo root (already gitignored).

**Step 2 — Authorise each Gmail account**

Run the setup script once per account from the repo root:

```powershell
cd apps\api
.venv\Scripts\python ..\..\scripts\gmail_setup.py
```

A browser window opens for OAuth consent. After authorising, the script prints three values — copy them into `.env`:

```ini
GMAIL_CLIENT_ID_1=…
GMAIL_CLIENT_SECRET_1=…
GMAIL_REFRESH_TOKEN_1=…
GMAIL_EMAIL_1=your.account@gmail.com
```

Repeat with `_2` and `_3` suffixes for additional accounts. Slots without all four fields are silently ignored.

---

## Configuration Reference

All settings live in `.env` (copy from `.env.example`).

### Gmail accounts

| Variable | Description |
|---|---|
| `GMAIL_EMAIL_N` | Email address for account N (N = 1, 2, 3) |
| `GMAIL_CLIENT_ID_N` | OAuth client ID |
| `GMAIL_CLIENT_SECRET_N` | OAuth client secret |
| `GMAIL_REFRESH_TOKEN_N` | OAuth refresh token |
| `GMAIL_WEIGHT_N` | Relative send weight — e.g. `50 / 30 / 20` gives ~50 % / 30 % / 20 % distribution |

### Sender identity

| Variable | Default | Description |
|---|---|---|
| `SENDER_NAME` | *(required)* | Your name as it appears in the From field |
| `SENDER_WEBSITE` | *(optional)* | Your website URL — injected via `{{sender_website}}` in templates |
| `CV_PATH` | `data/cv.pdf` | Absolute or relative path to a PDF file to attach; leave blank to disable |

### Send limits

| Variable | Default | Description |
|---|---|---|
| `DAILY_SEND_LIMIT_PER_ACCOUNT` | `30` | Max emails per Gmail account per day |
| `HOURLY_SEND_LIMIT_PER_ACCOUNT` | `5` | Max emails per Gmail account per hour |
| `MIN_DELAY_BETWEEN_SENDS_SEC` | `60` | Minimum seconds between two consecutive sends |
| `MAX_DELAY_BETWEEN_SENDS_SEC` | `180` | Maximum seconds between two consecutive sends |
| `COMPANY_WEEKLY_SEND_LIMIT` | `4` | Max contacts from the same company contacted per week |

### Email verification *(optional)*

| Variable | Description |
|---|---|
| `QUICKEMAILVERIFICATION_API_KEY` | Direct API key (takes priority over the file option) |
| `QUICKEMAILVERIFICATION_API_KEY_FILE` | Path to a plain-text file containing the key |
| `QUICKEMAILVERIFICATION_API_KEY_2` | Fallback key used when the primary key hits its quota |
| `EMAIL_VERIFICATION_TTL_DAYS` | Days before re-verifying an already-checked address (default: `30`) |

---

## Email Templates

Templates live in `data/templates/`. Each file is a Markdown document with a `Subject:` line on the first line.

### Naming convention

```
{step}_{lang}_{variant}.md
```

| Part | Values | Meaning |
|---|---|---|
| `step` | `intro`, `followup_1`, `followup_2` | Position in the sequence |
| `lang` | `fr`, `en` | Language — auto-detected from the contact's country |
| `variant` | `a`, `b`, … | A/B variant — rotated across sends |

**Example:** `intro_fr_a.md`, `followup_1_en_b.md`

### Template format

```markdown
Subject: Your subject line here

Body text with {{variables}} substituted at send time.
```

### Available variables

| Variable | Description |
|---|---|
| `{{civilite}}` | Honorific (`M.` or `Mme`) based on detected gender |
| `{{first_name}}` | Contact's first name |
| `{{last_name}}` | Contact's last name |
| `{{company}}` | Company name |
| `{{sender_name}}` | Your name, from `SENDER_NAME` in `.env` |
| `{{sender_email}}` | The Gmail address used for this specific send |
| `{{sender_website}}` | Your website URL, from `SENDER_WEBSITE` in `.env` |

Follow-up templates are rendered inside the original intro thread so recipients see a proper reply chain.

---

## Importing Contacts

Use the **Imports** tab and pick any CSV file via the file picker (or drag-and-drop).

The importer uses flexible column matching — these headers are all recognised:

| Field | Accepted column names |
|---|---|
| First name | `first_name`, `prospect_first_name` |
| Last name | `last_name`, `prospect_last_name` |
| Email | `email`, `contact_professions_email` |
| Company | `company`, `prospect_company_name` |
| Position | `position`, `prospect_job_title` |
| Country | `country`, `prospect_country_name` |
| LinkedIn | `linkedin`, `linkedin_url` |
| Gender | `sex`, `gender` |

Duplicate detection runs automatically on import (normalised email first, then name + company).

---

## Running a Campaign

1. **Import contacts** via the Imports tab.
2. Go to the **Campaigns** tab, enter a campaign name, and click **Prepare**.
3. Review the preparation summary — contact count, language split, account distribution, estimated duration.
4. Click **Start**. A live progress view shows each send in real time.
5. After sending, go to the **Replies** tab and click **Sync Replies** to pull new Gmail replies and auto-classify them.

Contacts who have already replied, been blocked, or were contacted too recently are automatically excluded from preparation.

---

## Contributing

Contributions are welcome. Please follow the architecture rules below so the codebase stays maintainable.

### Architecture rules

| Layer | Responsibility | Must NOT |
|---|---|---|
| `api/` routes | Validate input, call one service | Contain business logic or direct SQL |
| `services/` | All business logic | Execute raw SQL queries |
| `repositories/` | SQL queries only | Contain business logic |
| `models/` | SQLAlchemy table definitions | Anything else |
| `schemas/` | Pydantic request/response models | Anything else |
| `views/` | Render UI, trigger workers | Contain business logic |
| `workers/` | Run services off the main thread | Talk to the DB directly |

### Rules

- Functions stay under ~50 lines. Files stay under 300 lines.
- Type-annotate every function signature.
- Always normalise emails before insertion or lookup.
- Never commit a column removal without an Alembic migration.
- Never commit `.env`, `app.db`, `token*.json`, or any API key.
- One commit = one clear intention.

### Running the test suite

```powershell
cd apps\api
.venv\Scripts\activate
pytest
```

### Submitting a pull request

1. Fork the repository and create a feature branch from `main`.
2. Make your changes, keeping each commit focused.
3. Run `pytest` and make sure all tests pass.
4. Open a pull request against `main` with a clear description of what changed and why.

---

## License

MIT — see [`LICENSE`](LICENSE).
