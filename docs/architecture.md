# Architecture

## Vue d'ensemble

```
App prospection/
├── apps/
│   ├── api/          → Backend Python / FastAPI
│   └── web/          → Frontend React / TypeScript / Vite
├── data/
│   ├── imports/      → CSV déposés par l'utilisateur
│   ├── exports/      → CSV générés par l'application
│   └── app.db        → Base SQLite (généré au runtime, non versionné)
├── docs/             → Documentation technique
├── packages/
│   └── shared-types/ → Types TypeScript partagés (frontend ↔ contrat API)
├── scripts/          → Scripts manuels PowerShell
└── templates/        → Templates de mails en texte brut
```

---

## Backend : `apps/api/`

### Stack
- **FastAPI** : framework web asynchrone
- **SQLAlchemy** : ORM (mode Core + ORM)
- **Alembic** : migrations de base de données
- **Pydantic v2** : validation des données et schémas
- **SQLite** : base de données locale (migratable vers PostgreSQL)
- **Gmail API** : envoi et lecture des mails

### Organisation interne (`apps/api/app/`)

```
app/
├── api/           → Endpoints FastAPI (routes uniquement, pas de logique)
├── core/          → Config (pydantic-settings) + sécurité (JWT)
├── db/            → Session SQLAlchemy + base déclarative
├── models/        → Tables SQLAlchemy (ORM)
├── schemas/       → Modèles Pydantic (request / response)
├── repositories/  → Accès base de données (requêtes SQL)
├── services/      → Logique métier
├── utils/         → Utilitaires partagés (normalisation email, mapping CSV)
└── main.py        → Point d'entrée FastAPI
```

### Règle de flux de données
```
Route → Service → Repository → Base de données
```
Les routes ne contiennent que validation + appel de service.  
Toute la logique métier est dans `services/`.

### Détail des services (`app/services/`)

| Fichier | Rôle |
|---------|------|
| `csv_import_service.py` | Lecture, normalisation et import d'un CSV dans la base |
| `dedupe_service.py` | Fusion des doublons, détection des contacts déjà connus |
| `eligibility_service.py` | **Règles métier d'éligibilité** : répond à "ce contact peut-il être contacté maintenant ?" (déjà contacté ? répondu ? bounce ? délai relance atteint ? bloqué ? email valide ?) |
| `campaign_prepare_service.py` | **Préparation de campagne** : utilise `eligibility_service` pour filtrer les contacts, choisit le template et la boîte mail, génère la file d'attente d'envoi |
| `gmail_sent_contacts_service.py` | Parcourt les mails envoyés (`in:sent`) des deux boîtes pour marquer les contacts déjà contactés |
| `gmail_sync_service.py` | Lit les nouvelles réponses reçues, les associe aux contacts, met à jour la base |
| `mail_render_service.py` | Remplace les variables dans un template, génère le sujet et le corps du mail |
| `mail_send_service.py` | Envoie les mails via Gmail API, respecte les limites quotidiennes, enregistre le résultat |
| `reply_classification_service.py` | Analyse le texte d'une réponse, la classe (positive / négative / neutre / auto / à vérifier) |
| `followup_service.py` | Trouve les contacts sans réponse, vérifie le délai, prépare les relances |

> **Relation eligibility ↔ campaign_prepare** : `eligibility_service` ne sait rien des campagnes — il évalue un contact de façon isolée. `campaign_prepare_service` l'appelle en boucle sur tous les contacts pour construire la file d'envoi.

---

## Frontend : `apps/web/`

### Stack
- **React 19** + **TypeScript**
- **Vite** : bundler et dev server
- **TailwindCSS** : styles utilitaires
- **React Query (TanStack)** : gestion état serveur + cache
- **React Router v7** : navigation SPA
- **TanStack Table** : tableaux filtrables

### Organisation interne (`apps/web/src/`)

```
src/
├── app/
│   ├── providers.tsx  → Wrapping global (QueryClient, Router…)
│   └── router.tsx     → Définition des routes
├── components/
│   └── ui/            → Composants réutilisables (Button, Card, Table…)
├── features/          → Un dossier par section de l'interface
│   ├── dashboard/
│   ├── contacts/
│   ├── imports/
│   ├── campaigns/
│   └── replies/
├── lib/
│   ├── api-client.ts  → Toutes les fonctions fetch vers l'API
│   ├── query-client.ts
│   └── utils.ts
├── pages/             → Wrapping des vues (shell de layout)
└── types/
    └── api.ts         → Types correspondant aux schémas backend
```

### Règle absolue
Aucun `fetch` direct dans les composants. Tout appel API passe par `lib/api-client.ts`.

---

## Base de données

### Tables principales

| Table | Rôle |
|---|---|
| `contacts` | Contacts uniques (déduplication par email normalisé) |
| `campaign_states` | État d'un contact dans une campagne (envoi, relances, réponse) |
| `messages` | Historique de tous les mails envoyés |
| `replies` | Historique de toutes les réponses reçues |
| `imports` | Historique des imports CSV |

### Règle de déduplication
1. Clé primaire métier : **email normalisé** (lowercase, trim)
2. Fallback si pas d'email : prénom + nom + entreprise
3. Un mail d'introduction ne peut jamais être envoyé deux fois au même contact

---

## Intégration Gmail

Deux boîtes mail sont utilisées :
- `maxime.farre8@gmail.com` — envois secondaires
- `maxime@maxime-farre.xyz` — envois principaux

Chaque boîte est configurée via l'API Gmail (OAuth2).  
Les tokens OAuth sont stockés localement dans des fichiers non versionnés.

---

## Connexion future : OpenClaw

OpenClaw (agent IA) interagit **uniquement via l'API REST**.  
Il ne touche jamais directement la base SQLite.  
Endpoints prévus : `GET /contacts`, `POST /imports/csv`, `POST /campaigns/prepare`, `POST /campaigns/send`, `POST /replies/sync`.
