# AGENTS

Objectif : garder une architecture propre et éviter que les agents IA modifient le mauvais endroit.

## Règles générales

- Ne jamais mettre de logique métier dans React.
- Ne jamais accéder directement à la base SQLite depuis le frontend.
- Toutes les modifications passent par l'API FastAPI.
- OpenClaw ou tout autre agent ne doit jamais écrire directement dans la base.
- Toujours séparer :
  - UI
  - routes API
  - services métier
  - modèles SQL

## Frontend

Dossier : `apps/web/src/`

- `features/` : logique d'affichage par section
- `components/ui/` : composants réutilisables
- `lib/api-client.ts` : appels API
- Aucun fetch direct dans les composants.
- Aucun gros fichier > 300 lignes.

## Backend

Dossier : `apps/api/app/`

- `models/` : tables SQLAlchemy
- `schemas/` : modèles Pydantic
- `repositories/` : accès base de données
- `services/` : logique métier
- `api/` : endpoints FastAPI uniquement

Règle importante :
- Les routes ne doivent contenir que : validation + appel du service.
- Toute logique complexe doit aller dans `services/`.

## Base de données

- Un contact est unique par email normalisé.
- Ne jamais envoyer deux fois un mail d'introduction au même contact.
- Toute action importante doit être enregistrée dans la base.

## Modifications autorisées

Les agents IA peuvent :
- ajouter un nouvel endpoint
- ajouter un service
- créer un nouveau composant
- améliorer un template

Les agents IA ne doivent jamais :
- supprimer des colonnes SQL sans migration
- modifier directement `app.db`
- déplacer toute la logique dans un seul fichier
- dupliquer du code déjà existant
- casser les noms des endpoints déjà utilisés

## Style de code

- Fonctions courtes et lisibles
- Noms explicites
- Pas d'abréviations inutiles
- Commentaires uniquement si la logique n'est pas évidente
- Toujours typer les fonctions TypeScript et Python