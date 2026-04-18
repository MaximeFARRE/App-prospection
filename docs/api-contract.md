# Contrat API

Base URL : `http://localhost:8000`

---

## Contacts

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/contacts` | Liste paginée de tous les contacts |
| `GET` | `/contacts/{id}` | Détail d'un contact |
| `PATCH` | `/contacts/{id}` | Mise à jour partielle d'un contact |
| `DELETE` | `/contacts/{id}` | Suppression d'un contact |

---

## Imports CSV

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/imports/csv` | Upload et import d'un fichier CSV |
| `GET` | `/imports` | Historique des imports |
| `GET` | `/imports/{id}` | Détail d'un import (contacts créés, doublons…) |

---

## Campagnes

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/campaigns` | Liste des campagnes |
| `POST` | `/campaigns/prepare` | Prépare une campagne (sélection contacts éligibles) |
| `POST` | `/campaigns/send` | Lance l'envoi d'une campagne |
| `GET` | `/campaigns/{id}/status` | État d'avancement d'une campagne |

---

## Messages

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/messages` | Historique de tous les mails envoyés |
| `GET` | `/messages/{id}` | Détail d'un message |

---

## Réponses

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/replies` | Liste des réponses reçues |
| `POST` | `/replies/sync` | Synchronise les réponses depuis Gmail |
| `PATCH` | `/replies/{id}` | Met à jour la classification manuelle |

---

## Dashboard

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `GET` | `/dashboard/stats` | Statistiques globales (contacts, envois, réponses) |

---

## Conventions

- Tous les endpoints retournent du JSON.
- Les erreurs suivent le format `{ "detail": "message d'erreur" }`.
- La pagination utilise les query params `?skip=0&limit=50`.
- Les dates sont au format ISO 8601 (UTC).
- Les emails sont toujours renvoyés en minuscules normalisés.
