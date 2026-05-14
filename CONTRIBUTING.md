# Contributing to Prospection CRM

Thank you for taking the time to contribute. This document covers everything you need to know to submit a clean, reviewable change — from setting up your environment to opening a pull request.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Setting up the development environment](#setting-up-the-development-environment)
3. [Project structure recap](#project-structure-recap)
4. [Git workflow](#git-workflow)
5. [Branch naming](#branch-naming)
6. [Commit messages](#commit-messages)
7. [Code standards](#code-standards)
8. [Testing](#testing)
9. [Opening a pull request](#opening-a-pull-request)
10. [What not to do](#what-not-to-do)

---

## Prerequisites

| Tool | Minimum version | Notes |
|---|---|---|
| Python | 3.11 | Install from [python.org](https://www.python.org/downloads/) — check **Add Python to PATH** |
| Git | 2.x | [git-scm.com](https://git-scm.com/) |

---

## Setting up the development environment

```powershell
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/<your-username>/App-prospection.git
cd App-prospection

# 2. Add the upstream remote so you can pull future changes
git remote add upstream https://github.com/MaximeFARRE/App-prospection.git

# 3. Create the virtual environment and install dependencies
cd apps\api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 4. Set up your environment file
cd ..\..
copy .env.example .env
# Edit .env and fill in your Gmail credentials and SENDER_NAME

# 5. Run the test suite to verify everything is working
cd apps\api
pytest
```

> The virtual environment lives at `apps/api/.venv` and is shared by both the API and the desktop app.

---

## Project structure recap

```
apps/
├── api/app/
│   ├── api/            HTTP routes — validate input, call one service, return
│   ├── core/           Config (pydantic-settings) and security helpers
│   ├── db/             SQLAlchemy session and declarative base
│   ├── models/         ORM table definitions
│   ├── repositories/   SQL query layer
│   ├── schemas/        Pydantic request/response models
│   └── services/       All business logic — this is where most work happens
└── desktop/
    ├── views/          PyQt6 full-screen views — UI only, no business logic
    ├── widgets/        Dialogs and reusable components
    └── workers/        QThread workers for non-blocking service calls
```

**The golden rule:** business logic belongs in `services/`. Views and routes are thin wrappers that call a service and display the result.

---

## Git workflow

This project uses a **feature-branch workflow** against `main`.

```
main  ──────────────────────────────────────────────────────►
        │                          ▲
        └── feature/my-feature ────┘  (pull request)
```

### Step-by-step

```powershell
# 1. Make sure your local main is up to date
git checkout main
git pull upstream main

# 2. Create a feature branch (see naming rules below)
git checkout -b feat/add-linkedin-enrichment

# 3. Work in small, focused commits
#    (see commit message rules below)

# 4. Pull any upstream changes before opening a PR
git fetch upstream
git rebase upstream/main

# 5. Push your branch and open a pull request
git push -u origin feat/add-linkedin-enrichment
```

> **Never push directly to `main`.** All changes go through a pull request, even small ones.

---

## Branch naming

Use the format: `<type>/<short-description>`

| Type | When to use | Example |
|---|---|---|
| `feat/` | New feature or capability | `feat/reply-auto-archive` |
| `fix/` | Bug fix | `fix/followup-delay-off-by-one` |
| `test/` | Adding or fixing tests | `test/dedupe-service-coverage` |
| `refactor/` | Internal restructuring without behaviour change | `refactor/split-mail-send-service` |
| `docs/` | Documentation only | `docs/update-template-variables` |
| `chore/` | Maintenance (deps, config, CI) | `chore/bump-sqlalchemy-2-1` |

**Rules:**
- All lowercase, words separated by hyphens.
- Be specific — `feat/csv-import` is better than `feat/import`.
- Keep it under 50 characters.

---

## Commit messages

This project follows the [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <short summary>

[optional body — explain WHY, not what]

[optional footer — breaking changes, issue refs]
```

### Types

| Type | Use for |
|---|---|
| `feat` | A new feature visible to users |
| `fix` | A bug fix |
| `test` | Adding or correcting tests |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `docs` | Documentation only |
| `chore` | Build process, dependencies, tooling |
| `perf` | Performance improvement |

### Scopes (optional but recommended)

Use the layer or module name: `api`, `ui`, `services`, `db`, `templates`, `imports`, `replies`, `campaigns`.

### Examples

```
feat(campaigns): add per-account hourly send cap

fix(ui): fix unreadable text on replies tab — use dark green/red backgrounds

test(dedupe): add integration tests for merge_contacts and scan_duplicates

docs: rewrite README with badges and full setup guide

chore: upgrade pydantic-settings to 2.7
```

### Rules

- **Summary line:** imperative mood, no capital first letter, no trailing period, 72 chars max.
- **Body:** wrap at 72 chars, explain the *why* not the *what* — the diff already shows the what.
- **One commit = one intention.** If you need the word "and" to describe a commit, it should probably be two commits.
- **Never commit:** `.env`, `app.db`, `token*.json`, `credentials.json`, or any API key / OAuth token.

---

## Code standards

### Python

| Rule | Detail |
|---|---|
| Type annotations | Every function signature must be annotated |
| Function length | Max ~50 lines — split if longer |
| File length | Max 300 lines — split into modules if longer |
| Comments | Only when the *why* is non-obvious; never describe *what* the code does |
| Email handling | Always normalise emails before insertion or lookup |
| SQL | Only in `repositories/` — never in services or views |
| Commits | Never commit a column removal without an Alembic migration |

### Layer contracts

| Layer | Only responsibility | Must NOT |
|---|---|---|
| `api/` routes | Validate input, call one service | Contain business logic or raw SQL |
| `services/` | Business logic | Execute SQL queries directly |
| `repositories/` | SQL queries | Contain business logic |
| `models/` | SQLAlchemy table definitions | Anything else |
| `schemas/` | Pydantic request/response shapes | Anything else |
| `views/` | Render UI, trigger workers | Contain business logic |
| `workers/` | Run service calls off the main thread | Talk to the DB directly |

### PyQt6 (desktop)

- All long-running operations go in a `QThread` worker — never block the main thread.
- Workers emit signals; views connect to those signals. Workers never touch UI widgets directly.
- No business logic in views — delegate everything to a service via a worker.

---

## Testing

Every code change must be covered by tests. Run the full suite before pushing:

```powershell
cd apps\api
pytest
```

### What to test

- **New service function** → add unit tests in `tests/test_<service_name>.py`.
- **Bug fix** → add a regression test that fails without the fix and passes with it.
- **New API route** → test via the service layer, not via HTTP (no running server needed).
- **Pure utility function** → test all branches including edge cases (None inputs, empty strings, boundary values).

### What not to test

- PyQt6 views and widgets (UI rendering is not unit-testable without a display server).
- External API calls (Gmail, QuickEmailVerification) — mock at the boundary or skip.

### Test structure

```
tests/
├── conftest.py                    # shared fixtures (in-memory SQLite db)
├── test_<service_name>.py         # one file per service
└── …
```

Use the `db` fixture from `conftest.py` for all database tests — it provides a clean, isolated SQLite in-memory database for each test function.

```python
def test_something(db: Session) -> None:
    contact = Contact(email="a@example.com", email_normalized="a@example.com", sex="homme")
    db.add(contact)
    db.flush()
    # … assert …
```

---

## Opening a pull request

### Before you open

- [ ] All tests pass locally (`pytest` — zero failures).
- [ ] No new linting errors.
- [ ] `.env`, `*.db`, `token*.json` are not staged.
- [ ] Your branch is rebased on the latest `upstream/main`.

### PR title

Use the same Conventional Commits format as commit messages:

```
feat(replies): add bulk sentiment update action
fix(imports): handle CSV files with BOM encoding
```

### PR description template

```markdown
## What and why
<!-- One paragraph: what changed and why it was needed. -->

## How to test
<!-- Steps to manually verify the change in the desktop app. -->
- [ ] Step 1
- [ ] Step 2

## Checklist
- [ ] Tests added or updated
- [ ] No secrets committed
- [ ] README / .env.example updated if new config variables were added
```

### Scope of a PR

- **One PR = one coherent change.** A new feature and its tests can live in the same PR. An unrelated cleanup should be a separate PR.
- Keep PRs small enough to review in a single sitting (aim for under 400 lines changed).
- If a PR is large by necessity, add a summary comment that walks the reviewer through the changes in order.

---

## What not to do

These actions will cause a PR to be rejected:

- Removing a database column without an Alembic migration.
- Modifying `data/app.db` directly (it is gitignored for a reason).
- Putting business logic in a view, route, or worker.
- Calling the database directly from the desktop layer (all reads/writes go through the API layer).
- Duplicating existing service code instead of calling it.
- Committing secrets, OAuth tokens, or personal data of any kind.
- Opening a PR against a branch other than `main` without prior discussion.
