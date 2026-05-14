# Déploiement Supabase — Base collaborative

Guide pas à pas pour mettre en service la base collaborative.  
L'application fonctionne normalement sans Supabase (mode solo) — ce guide
est uniquement nécessaire si vous voulez activer le mode collaboratif.

---

## 1. Créer un projet Supabase

1. Aller sur [supabase.com](https://supabase.com) → **New project**
2. Choisir un nom (ex : `prospection-collab`), une région Europe et un mot de passe fort
3. Attendre la fin de la provisioning (~2 min)

---

## 2. Exécuter le schéma SQL

1. Dans le tableau de bord Supabase, ouvrir **SQL Editor** (icône `</>` dans la barre latérale)
2. Cliquer **New query**
3. Copier-coller l'intégralité de [`docs/supabase-schema.sql`](supabase-schema.sql)
4. Cliquer **Run** (ou `Ctrl+Entrée`)
5. Vérifier que la console affiche `Success. No rows returned` sur chaque instruction

> **Ordre d'exécution :** le script crée d'abord les tables, puis les index,
> puis active le RLS et crée les policies. L'ordre est important — ne pas
> l'exécuter en morceaux.

---

## 3. Récupérer les clés API

1. Dans le tableau de bord, aller dans **Project Settings** → **API**
2. Copier les valeurs suivantes :

| Clé | Emplacement dans l'interface | Usage |
|---|---|---|
| `Project URL` | Section *Project URL* | `SUPABASE_URL` |
| `anon public` | Section *Project API keys* | `SUPABASE_ANON_KEY` |

> **Ne jamais copier la `service_role` key** dans `.env` — elle bypasse le RLS
> et ne doit être utilisée que dans des Edge Functions côté serveur.

---

## 4. Configurer le `.env`

Ajouter ces deux lignes dans votre `.env` (en vous appuyant sur `.env.example`) :

```dotenv
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

Vérifier que `.env` est bien dans `.gitignore` avant de committer.

---

## 5. Créer le premier utilisateur

Le mode collaboratif utilise l'authentification Supabase intégrée (email + mot de passe).

1. Dans le tableau de bord → **Authentication** → **Users** → **Add user**
2. Saisir un email et un mot de passe
3. L'utilisateur peut maintenant se connecter depuis l'onglet **Paramètres** de l'application

> Pour permettre l'inscription libre (sans invitation admin), aller dans
> **Authentication** → **Providers** → **Email** et activer *Enable email confirmations*
> selon vos besoins.

---

## 6. Activer le mode collaboratif dans l'application

1. Lancer l'application desktop
2. Aller dans **Paramètres** → section **Base collaborative**
3. Cocher **Activer le mode collaboratif**
4. Saisir l'email et le mot de passe Supabase → cliquer **Connexion**
5. Le statut passe à `● Connecté` et l'onglet **Collaboratif** apparaît dans la sidebar

---

## 7. Vérification post-déploiement

```bash
# Depuis la racine du projet
pytest apps/api/tests/test_supabase_repository.py -v   # tests mockés (pas de réseau)
pytest apps/api/tests/ -v                              # suite complète
```

Vérifications manuelles :
- [ ] L'app se lance sans `SUPABASE_URL` dans `.env` → comportement solo inchangé
- [ ] Avec `SUPABASE_URL` mais toggle OFF → aucun appel réseau
- [ ] Toggle ON + connexion réussie → crédits affichés dans l'onglet Collaboratif
- [ ] `grep -r "SUPABASE_" . --include="*.py"` → résultats uniquement dans `config.py` et `supabase_repository.py`

---

## Schéma relationnel

```
users ──< contact_contributions >── contacts
users ──< contact_unlocks       >── contacts
users ──< contact_events (via email_hash)
```

La colonne `email_hash` (SHA-256) est l'unique identifiant de déduplication
cross-utilisateurs. L'email en clair n'est jamais stocké en V1 (`email_encrypted`
est réservé à une implémentation AES côté Edge Function en V2).
