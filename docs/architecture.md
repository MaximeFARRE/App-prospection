# Architecture

## Vue d'ensemble

```
App prospection/
├── apps/
│   ├── api/          → Backend Python / FastAPI (OpenClaw uniquement)
│   └── desktop/      → Interface PyQt6 (application principale)
├── data/
│   ├── imports/      → CSV déposés par l'utilisateur
│   ├── exports/      → CSV générés par l'application
│   └── app.db        → Base SQLite (généré au runtime, non versionné)
├── docs/             → Documentation technique
├── scripts/          → Scripts PowerShell
└── templates/        → Templates de mails en texte brut
```

---

## Principe général

L'application est **100 % Python**.

```
desktop/ (PyQt6)
    │
    ├── importe directement ──→ apps/api/app/services/
    │                                   │
    │                                   └──→ apps/api/app/repositories/
    │                                                   │
    │                                                   └──→ SQLite (data/app.db)
    │
    └── (optionnel) HTTP ──→ FastAPI ──→ OpenClaw
```

Le desktop appelle les **services directement** (pas de HTTP pour l'usage normal).
FastAPI ne tourne que si OpenClaw doit se connecter.

Un seul environnement virtuel : `apps/api/.venv`, partagé par les deux apps.

---

## Desktop : `apps/desktop/`

### Stack
- **PyQt6** : interface graphique native Windows/macOS/Linux
- Imports directs des services métier depuis `apps/api/app/`

### Organisation

```
desktop/
├── main.py           → Point d'entrée : QApplication + création BDD + fenêtre
└── views/
    ├── main_window.py    → Fenêtre principale (sidebar + QStackedWidget)
    ├── dashboard_view.py → Stats globales
    ├── contacts_view.py  → Tableau des contacts
    ├── imports_view.py   → Import de CSV
    ├── campaigns_view.py → Préparation et envoi des campagnes
    ├── replies_view.py   → Réponses reçues
    └── settings_view.py  → Configuration (comptes Gmail, limites…)
```

### Règle absolue
Les vues ne contiennent **aucune logique métier**.
Toute action appelle un service de `apps/api/app/services/`.

---

## Backend : `apps/api/`

### Rôle
Exposer les endpoints REST **pour OpenClaw uniquement**.
Toute la logique métier reste dans `app/services/` et `app/repositories/`.

### Stack
- **FastAPI** + **Uvicorn**
- **SQLAlchemy** + **Alembic**
- **Pydantic v2**
- **Gmail API** (OAuth2)

### Organisation interne (`apps/api/app/`)

```
app/
├── api/           → Endpoints FastAPI (routes uniquement)
├── core/          → Config (pydantic-settings) + sécurité
├── db/            → Session SQLAlchemy + Base déclarative
├── models/        → Tables SQLAlchemy
├── schemas/       → Modèles Pydantic request/response
├── repositories/  → Requêtes SQL
├── services/      → Logique métier (partagée avec le desktop)
├── utils/         → Normalisation email, mapping CSV
└── main.py        → Point d'entrée FastAPI
```

### Détail des services

| Fichier | Rôle |
|---------|------|
| `csv_import_service.py` | Lecture, normalisation et import CSV |
| `dedupe_service.py` | Fusion des doublons |
| `eligibility_service.py` | Règles d'éligibilité d'un contact (bloqué ? déjà contacté ? délai relance ?) |
| `campaign_prepare_service.py` | Utilise eligibility_service pour construire la file d'envoi |
| `gmail_sent_contacts_service.py` | Parcourt les envois Gmail pour marquer les contacts déjà contactés |
| `gmail_sync_service.py` | Synchronise les réponses reçues |
| `mail_render_service.py` | Remplace les variables dans les templates |
| `mail_send_service.py` | Envoie les mails via Gmail API |
| `reply_classification_service.py` | Classifie les réponses (positif / négatif / neutre…) |
| `followup_service.py` | Prépare les relances |

---

## Base de données

| Table | Rôle |
|---|---|
| `contacts` | Contacts uniques (clé : email normalisé) |
| `campaign_states` | État d'un contact dans une campagne |
| `messages` | Historique des mails envoyés |
| `replies` | Historique des réponses reçues |
| `imports` | Historique des imports CSV |

---

## Lancement

```powershell
.\scripts\dev-start.ps1
```

Ou manuellement :
```powershell
cd apps/api
.venv\Scripts\activate
python ..\desktop\main.py
```
