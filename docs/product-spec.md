# Spécification produit

## Objectif

CRM personnel de prospection pour stages et candidatures en finance.

Centraliser tous les contacts, éviter les doublons, préparer des campagnes de mails, suivre les réponses, et connecter plus tard le système à OpenClaw.

---

## Fonctionnalités principales

| # | Fonctionnalité | Priorité |
|---|---------------|---------|
| 1 | Import de CSV de prospects | Haute |
| 2 | Fusion et déduplication des contacts | Haute |
| 3 | Suivi des contacts déjà contactés (historique Gmail) | Haute |
| 4 | Gestion de campagnes d'envoi | Haute |
| 5 | Envoi automatique de mails personnalisés | Haute |
| 6 | Synchronisation et classification des réponses | Haute |
| 7 | Relances automatiques | Moyenne |
| 8 | Pilotage par OpenClaw | Basse (future) |

---

## Interface utilisateur

Application monopage avec barre de navigation :

### Dashboard
- Nombre de contacts total
- Nombre de mails envoyés
- Nombre de réponses reçues
- Taux de réponse
- Réponses positives / négatives

### Contacts
Tableau filtrable :
- Prénom, nom, entreprise, email, statut, dernier mail envoyé

### Imports
- Upload de fichiers CSV
- Historique des imports avec compteur de contacts créés / doublons ignorés

### Campaigns
- Sélection des contacts éligibles
- Choix du template
- Lancement de l'envoi (avec respect des limites quotidiennes)

### Replies
- Liste des réponses reçues
- Classification : positive / négative / neutre / automatique / à vérifier
- Actions suggérées (relance, archivage…)

---

## Règles métier critiques

1. Un contact est unique par son **email normalisé**.
2. Un mail d'introduction **ne peut jamais être envoyé deux fois** au même contact.
3. Si un contact a répondu, **aucune relance automatique** n'est envoyée.
4. Si une adresse rebondit ou est invalide, elle est **bloquée**.
5. Toutes les actions importantes sont **enregistrées** dans la base.
6. Limite d'envoi : **20 à 30 mails / jour / boîte** avec délai aléatoire entre envois.

---

## Comptes mail

| Boîte | Adresse | Usage |
|-------|---------|-------|
| Compte 1 | `maxime.farre8@gmail.com` | Envois secondaires, secours |
| Compte 2 | `maxime@maxime-farre.xyz` | Envois principaux, image pro |

---

## Templates prévus

Dossier `templates/` à la racine du projet :

| Fichier | Usage |
|---------|-------|
| `intro_rh_asset_management.txt` | Introduction RH – Asset Management |
| `intro_private_equity.txt` | Introduction – Private Equity |
| `intro_family_office.txt` | Introduction – Family Office |
| `intro_small_company.txt` | Introduction – PME / Petite structure |
| `followup_1.txt` | Relance 1 |
| `followup_2.txt` | Relance 2 |

Variables disponibles dans les templates : `{{prenom}}`, `{{nom}}`, `{{entreprise}}`, `{{poste}}`, `{{campagne}}`.

---

## Ordre de développement conseillé

1. Base SQLite + modèles SQLAlchemy
2. Import CSV + déduplication
3. Dashboard + liste des contacts
4. Récupération des contacts déjà contactés depuis Gmail (`in:sent`)
5. Préparation et envoi des campagnes
6. Synchronisation et classification des réponses
7. Relances automatiques
8. Connexion à OpenClaw
