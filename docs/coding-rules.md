# Règles de code

## Règles générales

- Fonctions courtes et lisibles (max ~50 lignes).
- Noms explicites, pas d'abréviations inutiles.
- Aucun fichier > 300 lignes — découper si nécessaire.
- Commentaires uniquement si la logique n'est pas évidente.
- Toujours typer les fonctions (TypeScript et Python).

---

## Backend Python

### Couches et responsabilités

| Dossier | Responsabilité | Ce qu'il NE doit PAS faire |
|---------|---------------|---------------------------|
| `api/` | Validation entrée + appel service | Logique métier, SQL direct |
| `services/` | Logique métier | Requêtes SQL directes |
| `repositories/` | Requêtes SQL | Logique métier |
| `models/` | Déclaration tables SQLAlchemy | Rien d'autre |
| `schemas/` | Modèles Pydantic request/response | Rien d'autre |

### Règles spécifiques

- Toujours utiliser Pydantic pour valider les entrées des routes.
- Ne jamais `commit` depuis un service — laisser la session au repository.
- Toujours normaliser les emails avant toute insertion ou recherche.
- Ne jamais supprimer de colonnes sans migration Alembic.
- Ne jamais modifier `data/app.db` directement.

---

## Frontend TypeScript / React

### Règles de composants

- Aucun `fetch` ou `axios` direct dans un composant.
- Tous les appels API passent par `lib/api-client.ts`.
- Utiliser React Query pour la gestion du cache serveur.
- Les composants dans `features/` sont spécifiques à une section.
- Les composants dans `components/ui/` sont génériques et réutilisables.

### Règles de typage

- Tous les types correspondant à l'API sont dans `types/api.ts`.
- Aucun `any` sauf si absolument inévitable et commenté.

---

## Git

- Un commit = une intention claire.
- Ne jamais commiter `.env`, `app.db`, `node_modules/`, `token*.json`.
- Ne jamais commiter de clés API ou tokens Gmail.

---

## Ce que les agents IA peuvent faire

- Ajouter un nouvel endpoint.
- Ajouter un service.
- Créer un nouveau composant.
- Améliorer un template de mail.

## Ce que les agents IA ne doivent jamais faire

- Supprimer des colonnes SQL sans migration.
- Modifier directement `app.db`.
- Déplacer toute la logique dans un seul fichier.
- Dupliquer du code existant.
- Casser les noms des endpoints déjà utilisés.
- Accéder directement à la base depuis le frontend.
