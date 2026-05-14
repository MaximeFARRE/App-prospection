# Plan d'implémentation — Feature collaborative Supabase

> **Statut :** À implémenter  
> **Branche :** `feature/collaborative-supabase`  
> **Règle de commit :** 1 commit toutes les ~100 lignes modifiées  
> **Principe cardinal :** ne pas casser l'existant — la feature est 100 % optionnelle

---

## Contexte et objectif

L'application de prospection existante permet déjà d'envoyer des mails via Gmail API et stocke les contacts en SQLite local. Cette feature ajoute une **couche collaborative optionnelle** via Supabase permettant à plusieurs utilisateurs de partager une base de contacts, sans exposer toute la base.

**Règles produit :**
- L'app fonctionne normalement sans Supabase (mode solo)
- Le mode collaboratif s'active/désactive dans les paramètres
- Les contacts partagés ne sont pas tous visibles d'un coup
- L'utilisateur gagne des crédits en contribuant des contacts valides
- Les crédits débloquent progressivement des contacts partagés
- Un contact déjà contacté par un autre utilisateur est filtré avant envoi

---

## Architecture cible

```
UI (PyQt6)
  └── CollaborativeView / SettingsView (toggle)
        └── CollaborativeWorkers (QThread)
              └── CollaborativeService       ← toute la logique métier
                    ├── ContactValidationService
                    ├── SupabaseRepository   ← accès Supabase uniquement
                    └── [services existants inchangés]
```

**Principe :** Supabase est une dépendance optionnelle injectée. Si `enabled = False`, aucun appel réseau, aucun import Supabase dans le chemin critique.

---

## Étape 0 — Branche et configuration

**Objectif :** poser les fondations de config sans toucher au code métier.

### 0.1 Créer la branche

```bash
git checkout -b feature/collaborative-supabase
```

### 0.2 Mettre à jour `.env.example`

Ajouter à la fin du fichier `.env.example` :

```dotenv
# ── Supabase (optionnel — mode collaboratif) ──────────────────────────────────
SUPABASE_URL=
SUPABASE_ANON_KEY=
# NE PAS committer la service_role_key — uniquement pour les Edge Functions
# SUPABASE_SERVICE_ROLE_KEY=
```

### 0.3 Ajouter `SupabaseSettings` dans `apps/api/app/core/config.py`

Ajouter après les settings existants :

```python
class SupabaseSettings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

supabase_settings = SupabaseSettings()
```

### 0.4 Étendre `data/settings.json` schema dans `apps/desktop/services/settings_service.py`

Ajouter la clé `collaborative` dans la structure de settings par défaut :

```python
DEFAULT_COLLABORATIVE = {
    "enabled": False,
    "user_id": None,        # UUID Supabase de l'utilisateur connecté
    "user_email": None,
    "credits": 0,
    "last_sync_at": None,
}
```

Ajouter les méthodes :
- `get_collaborative_config() -> dict`
- `save_collaborative_config(config: dict) -> None`
- `set_collaborative_enabled(value: bool) -> None`

### 0.5 Ajouter la dépendance Python

Dans `apps/api/requirements.txt` :
```
supabase>=2.0.0
```

### Commit attendu
> `feat(collab): add Supabase config scaffold and settings schema`  
> ~40 lignes modifiées

---

## Étape 1 — Migration SQLite locale

**Objectif :** étendre la base locale sans casser les données existantes.

### 1.1 Modifier `apps/api/app/models/contact.py`

Ajouter deux colonnes nullables à la classe `Contact` :

```python
collab_source_id: Mapped[Optional[str]] = mapped_column(
    String(36), nullable=True, index=True
)  # UUID du contact dans la base Supabase
collab_is_contributed: Mapped[bool] = mapped_column(
    Boolean, default=False, nullable=False
)  # True si ce contact a été contribué à la base collaborative
```

### 1.2 Créer la table locale de cache des contacts débloqués

Nouveau fichier `apps/api/app/models/collaborative_state.py` :

```python
class CollabUnlockedCache(Base):
    """Contacts débloqués depuis Supabase, stockés localement pour usage hors-ligne."""
    __tablename__ = "collab_unlocked_cache"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    supabase_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    first_name: Mapped[Optional[str]]
    last_name: Mapped[Optional[str]]
    job_title: Mapped[Optional[str]]
    company_name: Mapped[Optional[str]]
    country: Mapped[Optional[str]]
    linkedin_url: Mapped[Optional[str]]
    quality_score: Mapped[int] = mapped_column(Integer, default=0)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    imported_to_local: Mapped[bool] = mapped_column(Boolean, default=False)
```

### 1.3 Créer la migration Alembic

```bash
cd apps/api
alembic revision --autogenerate -m "add collaborative fields to contacts and collab_unlocked_cache"
```

Vérifier le script généré dans `alembic/versions/`.

### 1.4 Ajouter `collaborative_state.py` dans `apps/api/app/db/base.py`

```python
from app.models.collaborative_state import CollabUnlockedCache  # noqa
```

### Commit attendu
> `feat(collab): add collaborative columns to Contact and ColabUnlockedCache table`  
> ~80 lignes

---

## Étape 2 — `SupabaseRepository`

**Objectif :** isoler tout accès réseau Supabase dans une seule classe.

### 2.1 Créer `apps/api/app/repositories/supabase_repository.py`

```python
"""
Accès Supabase — couche repository pure, pas de logique métier.
Toutes les méthodes retournent None / [] si le client n'est pas initialisé.
"""
from __future__ import annotations
from typing import Optional
import hashlib


def _hash_email(email: str) -> str:
    """SHA-256 de l'email normalisé (minuscules, sans espaces)."""
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()
```

**Méthodes à implémenter :**

| Méthode | Description |
|---|---|
| `__init__(supabase_client)` | Reçoit le client par injection |
| `get_user_credits(user_id: str) -> int` | Retourne les crédits courants |
| `get_unlocked_count(user_id: str) -> int` | Nombre de contacts débloqués |
| `get_unlocked_contacts(user_id: str, since: Optional[datetime]) -> list[dict]` | Contacts débloqués (delta sync) |
| `upsert_contact(email: str, metadata: dict) -> Optional[str]` | Insère ou met à jour, retourne l'UUID Supabase |
| `create_contribution(user_id: str, contact_id: str) -> bool` | Enregistre la contribution |
| `request_unlock(user_id: str, count: int) -> list[dict]` | Demande X déblocages, retourne contacts déchiffrés |
| `record_contact_event(email: str, event_type: str, user_id: str) -> None` | Poste un événement (contacted/replied/bounced) |
| `check_already_contacted(email_list: list[str]) -> set[str]` | Retourne les hashes déjà contactés par n'importe quel user |
| `login(email: str, password: str) -> Optional[dict]` | Auth Supabase, retourne session |
| `logout() -> None` | Déconnexion |

**Règles :**
- Chaque méthode `try/except` avec log d'erreur, retourne valeur nulle en cas d'échec réseau
- Jamais d'email en clair dans `contacts.email_hash` — utiliser `_hash_email()`
- L'email en clair passe uniquement via `email_encrypted` (chiffrement à ajouter en V2 — V1 : champ omis, contacts non déchiffrables côté client sans Edge Function)

### Commit attendu
> `feat(collab): implement SupabaseRepository with all data access methods`  
> ~120 lignes → commit dès 100 lignes

---

## Étape 3 — `CollaborativeService`

**Objectif :** toute la logique métier collaborative dans un seul service.

### 3.1 Créer `apps/api/app/services/collaborative_service.py`

**Dépendances injectées :**
```python
class CollaborativeService:
    def __init__(
        self,
        supabase_repo: SupabaseRepository,
        contact_validation_service: ContactValidationService,
        db: Session,
        user_id: str,
        enabled: bool = False,
    ): ...
```

**Méthodes à implémenter :**

| Méthode | Logique |
|---|---|
| `is_enabled() -> bool` | Retourne `self.enabled` |
| `get_credits() -> int` | Lit depuis repo + met à jour settings.json |
| `refresh_credits() -> int` | Force sync depuis Supabase |
| `contribute_contact(contact: Contact) -> ContributionResult` | Valide → hash email → upsert → create_contribution |
| `unlock_contacts(count: int) -> list[dict]` | Vérifie crédits ≥ count → request_unlock → store_locally |
| `sync_unlocked_locally(db: Session) -> int` | Delta sync depuis `last_sync_at` → insère dans `collab_unlocked_cache` |
| `is_already_contacted_by_others(email: str) -> bool` | check_already_contacted([email]) |
| `filter_already_contacted(contacts: list) -> list` | Batch check, retire les contacts déjà contactés |
| `record_send_event(email: str) -> None` | record_contact_event(email, 'contacted') |
| `import_unlocked_to_local(db: Session) -> int` | Copie contacts de `collab_unlocked_cache` vers `contacts` SQLite |

**Dataclass résultat :**
```python
@dataclass
class ContributionResult:
    success: bool
    contact_id: Optional[str]
    credits_awarded: int
    rejection_reason: Optional[str]
```

### Commit attendu
> `feat(collab): implement CollaborativeService business logic`  
> ~100 lignes → commit

---

## Étape 4 — `ContactValidationService`

**Objectif :** scorer la qualité d'un contact avant contribution.

### 4.1 Créer `apps/api/app/services/contact_validation_service.py`

**Score pondéré 0–100 :**

| Critère | Points |
|---|---|
| Email présent et format valide | 25 |
| Email vérifié par QEV (status=valid) | 20 |
| Domaine professionnel (pas gmail/hotmail/yahoo/etc.) | 15 |
| Prénom ET nom renseignés | 15 |
| Company renseignée | 15 |
| URL LinkedIn valide | 10 |

**Méthodes :**

```python
class ContactValidationService:
    def __init__(self, threshold: int = 60): ...

    def score(self, contact: Contact) -> int:
        """Retourne un score 0-100."""

    def validate(self, contact: Contact) -> ValidationResult:
        """Retourne (is_valid, score, rejection_reason)."""

    def _is_professional_domain(self, email: str) -> bool:
        """Vérifie que le domaine n'est pas un fournisseur grand public."""
```

**Domaines exclus (liste non exhaustive) :**
`gmail.com, hotmail.com, hotmail.fr, yahoo.com, yahoo.fr, outlook.com, live.com, free.fr, orange.fr, wanadoo.fr, laposte.net, sfr.fr`

**Dataclass résultat :**
```python
@dataclass
class ValidationResult:
    is_valid: bool
    score: int
    rejection_reason: Optional[str]
```

### Commit attendu
> `feat(collab): implement ContactValidationService with quality scoring`  
> ~80 lignes

---

## Étape 5 — Intégration dans le flow d'envoi existant

**Objectif :** brancher la déduplication collaborative dans le pipeline d'envoi sans refactorer.

> ⚠️ C'est la seule étape qui touche au code existant. Modifications minimales uniquement.

### 5.1 Modifier `apps/api/app/services/campaign_prepare_service.py`

Dans la boucle d'éligibilité, ajouter un check optionnel **après** les checks existants :

```python
# Injection optionnelle — None si mode solo
collaborative_service: Optional[CollaborativeService] = None

def prepare_campaign(
    ...,
    collaborative_service: Optional[CollaborativeService] = None,
) -> ...:
    ...
    for contact in eligible_contacts:
        # [checks existants inchangés]
        ...
        # Check collaboratif optionnel
        if collaborative_service and collaborative_service.is_enabled():
            if collaborative_service.is_already_contacted_by_others(contact.email):
                stats.skipped_already_contacted_by_others += 1
                continue
        queue.append(contact)
```

**Ajouter `skipped_already_contacted_by_others: int = 0` à `CampaignStats`.**

### 5.2 Modifier `apps/api/app/services/mail_send_service.py`

Après chaque envoi réussi, poster l'événement :

```python
def send_campaign(
    ...,
    collaborative_service: Optional[CollaborativeService] = None,
) -> ...:
    ...
    # après message enregistré en base :
    if collaborative_service and collaborative_service.is_enabled():
        collaborative_service.record_send_event(contact.email)
```

### 5.3 Modifier `apps/desktop/workers/campaign_workers.py`

Instancier et passer le `CollaborativeService` si enabled :

```python
collab_service = None
if settings_service.get_collaborative_config().get("enabled"):
    # init client Supabase + service
    collab_service = _build_collaborative_service(settings_service)

worker = CampaignSendWorker(queue, campaign_name, db, collaborative_service=collab_service)
```

### Commit attendu
> `feat(collab): wire CollaborativeService into campaign prepare and send pipeline`  
> ~60 lignes

---

## Étape 6 — UI Desktop

**Objectif :** exposer la feature dans l'interface sans logique métier dans les vues.

### 6.1 Modifier `apps/desktop/views/settings_view.py`

Ajouter une section "Base collaborative" en bas de la page paramètres :

```
┌─ Base collaborative ──────────────────────────────────────────┐
│  [✓] Activer le mode collaboratif                             │
│                                                               │
│  Email Supabase : [________________________]                  │
│  Mot de passe   : [________________________]  [Connexion]     │
│                                                               │
│  Statut : ● Connecté — 12 crédits disponibles                 │
└───────────────────────────────────────────────────────────────┘
```

- Toggle `QCheckBox` → `settings_service.set_collaborative_enabled()`
- Bouton Connexion → lance `SupabaseLoginWorker`
- Statut mis à jour par signal worker

### 6.2 Créer `apps/desktop/views/collaborative_view.py`

Onglet complet visible uniquement si `enabled = True` :

```
┌─ Base collaborative ──────────────────────────────────────────┐
│  Crédits : ██████░░░░  12 / 20     [↻ Rafraîchir]            │
│                                                               │
│  [Contribuer des contacts]    [Débloquer 5 contacts (5 crédits)]│
│                                                               │
│  ┌─ Contacts débloqués (34) ───────────────────────────────┐  │
│  │  Prénom  Nom         Société          Pays  [Importer]   │  │
│  │  Alice   Martin      Acme Corp        FR    [✓ Importé]  │  │
│  │  Bob     Dupont      Tech SA          FR    [Importer]   │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

**Signaux attendus :**
- `credits_updated(int)` → met à jour la barre de crédits
- `contacts_synced(list)` → rafraîchit le tableau
- `contribution_done(ContributionResult)` → affiche succès/erreur

### 6.3 Créer `apps/desktop/workers/collaborative_workers.py`

```python
class SyncCreditsWorker(QThread):
    credits_updated = pyqtSignal(int)
    ...

class UnlockContactsWorker(QThread):
    contacts_unlocked = pyqtSignal(list)
    error = pyqtSignal(str)
    ...

class ContributeContactWorker(QThread):
    contribution_done = pyqtSignal(dict)  # ContributionResult as dict
    ...

class SupabaseLoginWorker(QThread):
    login_success = pyqtSignal(str)  # user_id
    login_failed = pyqtSignal(str)   # message d'erreur
    ...
```

### 6.4 Modifier `apps/desktop/views/main_window.py`

```python
def _setup_tabs(self):
    ...
    if self.settings_service.get_collaborative_config().get("enabled"):
        self.tab_widget.addTab(CollaborativeView(...), "Base collaborative")
```

Reconnecter les onglets si le toggle change dans Settings (signal `collaborative_toggled`).

### Commits attendus
> Faire un commit par sous-étape (~100 lignes chacun) :  
> - `feat(collab): add collaborative section in settings view`  
> - `feat(collab): implement CollaborativeView with credits and contact list`  
> - `feat(collab): add collaborative QThread workers`  
> - `feat(collab): wire collaborative tab in main window`

---

## Étape 7 — Tests

**Objectif :** couvrir la logique crédits, validation, déduplication et sync.

### 7.1 `apps/api/tests/test_contact_validation_service.py`

```python
def test_valid_professional_contact_scores_high()
def test_missing_email_scores_zero()
def test_generic_domain_penalized()         # gmail.com, hotmail.fr...
def test_invalid_email_format_rejected()
def test_missing_first_name_reduces_score()
def test_missing_company_reduces_score()
def test_linkedin_url_adds_points()
def test_score_below_threshold_is_invalid()
def test_threshold_configurable()
```

### 7.2 `apps/api/tests/test_collaborative_service.py`

```python
def test_contribute_valid_contact_creates_contribution()
def test_contribute_invalid_contact_returns_rejection()
def test_credits_returned_as_integer()
def test_unlock_stores_contacts_in_local_db()
def test_disabled_service_skips_all_network_calls()
def test_filter_already_contacted_removes_matching_emails()
def test_record_send_event_calls_repo()
def test_import_unlocked_to_local_creates_contacts()
```

### 7.3 `apps/api/tests/test_collab_dedupe.py`

```python
def test_email_hash_normalization_case_insensitive()
def test_email_hash_normalization_strips_spaces()
def test_already_contacted_filter_batch()
def test_no_duplicate_contribution_same_contact()
def test_local_contact_not_duplicated_on_import()
```

### 7.4 `apps/api/tests/test_supabase_repository.py`

Utiliser un mock du client Supabase (`unittest.mock.MagicMock`) :

```python
def test_get_user_credits_returns_int()
def test_upsert_contact_idempotent()
def test_check_already_contacted_batch()
def test_request_unlock_respects_count()
def test_repo_returns_empty_on_network_error()  # client.table().select() lève une exception
def test_hash_email_consistent()
```

### Commit attendu
> `test(collab): add unit tests for validation, service, dedupe and repo`  
> ~150 lignes → 1-2 commits

---

## Étape 8 — Schéma Supabase et déploiement

**Objectif :** déployer les tables et policies sur le projet Supabase.

### 8.1 Créer `docs/supabase-schema.sql`

Script SQL complet à exécuter dans l'éditeur SQL Supabase :

```sql
-- ── TABLES ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT UNIQUE NOT NULL,
  display_name  TEXT,
  credits       INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.contacts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_hash      TEXT UNIQUE NOT NULL,
  email_encrypted TEXT,
  first_name      TEXT,
  last_name       TEXT,
  job_title       TEXT,
  company_name    TEXT,
  country         TEXT,
  linkedin_url    TEXT,
  email_status    TEXT DEFAULT 'unknown',
  quality_score   INT DEFAULT 0,
  is_visible      BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.contact_contributions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID REFERENCES public.users(id) ON DELETE CASCADE,
  contact_id        UUID REFERENCES public.contacts(id) ON DELETE CASCADE,
  submitted_at      TIMESTAMPTZ DEFAULT now(),
  validation_status TEXT DEFAULT 'pending',
  credits_awarded   INT DEFAULT 0,
  UNIQUE(user_id, contact_id)
);

CREATE TABLE IF NOT EXISTS public.contact_unlocks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES public.users(id) ON DELETE CASCADE,
  contact_id  UUID REFERENCES public.contacts(id) ON DELETE CASCADE,
  unlocked_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, contact_id)
);

CREATE TABLE IF NOT EXISTS public.contact_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_hash  TEXT NOT NULL,
  event_type  TEXT NOT NULL CHECK (event_type IN ('contacted', 'replied', 'bounced')),
  user_id     UUID REFERENCES public.users(id),
  occurred_at TIMESTAMPTZ DEFAULT now()
);

-- ── INDEX ────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_contact_events_hash ON public.contact_events(email_hash);
CREATE INDEX IF NOT EXISTS idx_unlocks_user ON public.contact_unlocks(user_id);
CREATE INDEX IF NOT EXISTS idx_contributions_user ON public.contact_contributions(user_id);

-- ── ROW LEVEL SECURITY ───────────────────────────────────────────────────────

ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_unlocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- contacts : visible uniquement si débloqué par l'utilisateur courant
CREATE POLICY "contacts_unlock_gate" ON public.contacts
  FOR SELECT USING (
    id IN (
      SELECT contact_id FROM public.contact_unlocks
      WHERE user_id = auth.uid()
    )
  );

-- contributions : chacun voit seulement les siennes
CREATE POLICY "own_contributions_only" ON public.contact_contributions
  FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "insert_own_contribution" ON public.contact_contributions
  FOR INSERT WITH CHECK (user_id = auth.uid());

-- contact_events : lecture globale (déduplication inter-users)
CREATE POLICY "events_read_all" ON public.contact_events
  FOR SELECT USING (true);

CREATE POLICY "events_insert_own" ON public.contact_events
  FOR INSERT WITH CHECK (user_id = auth.uid());

-- users : chacun voit son propre profil
CREATE POLICY "own_profile" ON public.users
  FOR SELECT USING (id = auth.uid());

CREATE POLICY "own_profile_update" ON public.users
  FOR UPDATE USING (id = auth.uid());
```

### 8.2 Créer `docs/supabase-deploy.md`

Guide de déploiement pas à pas (création projet Supabase, exécution du SQL, récupération des clés, remplissage du `.env`).

### Commit attendu
> `docs(collab): add Supabase SQL schema and deployment guide`  
> ~80 lignes SQL + doc

---

## Checklist de validation finale

Avant de merger sur `main` :

- [ ] `pytest apps/api/tests/` passe à 100 % (tests existants + nouveaux)
- [ ] `pytest apps/desktop/tests/` passe
- [ ] L'app se lance sans Supabase configuré (`enabled = False`) → comportement identique à l'existant
- [ ] L'app se lance avec Supabase configuré → onglet "Base collaborative" visible
- [ ] Un toggle OFF dans les paramètres masque l'onglet immédiatement
- [ ] Aucune clé Supabase dans le code (grep `SUPABASE_` → uniquement `.env.example` et `config.py`)
- [ ] Les tests existants de `campaign_prepare_service` passent sans passer de `CollaborativeService`
- [ ] Un contact local existant n'est pas dupliqué lors de l'import depuis `collab_unlocked_cache`

---

## Références

| Fichier | Rôle |
|---|---|
| `apps/api/app/core/config.py` | `SupabaseSettings` |
| `apps/api/app/repositories/supabase_repository.py` | Accès données Supabase |
| `apps/api/app/services/collaborative_service.py` | Logique crédits / déblocages / sync |
| `apps/api/app/services/contact_validation_service.py` | Score qualité contact |
| `apps/api/app/models/collaborative_state.py` | Cache local SQLite |
| `apps/desktop/views/collaborative_view.py` | Onglet UI |
| `apps/desktop/views/settings_view.py` | Toggle + login Supabase |
| `apps/desktop/workers/collaborative_workers.py` | Workers QThread |
| `docs/supabase-schema.sql` | Script SQL Supabase |
| `apps/api/tests/test_collaborative_service.py` | Tests service |
| `apps/api/tests/test_contact_validation_service.py` | Tests validation |
| `apps/api/tests/test_collab_dedupe.py` | Tests déduplication |
| `apps/api/tests/test_supabase_repository.py` | Tests repository (mock) |
