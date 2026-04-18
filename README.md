# App Prospection

CRM personnel de prospection pour stages et candidatures en finance.

Objectif : centraliser tous les contacts, éviter les doublons, préparer des campagnes de mails, suivre les réponses, et connecter plus tard le système à OpenClaw.

---

# Objectif du projet

L'application doit permettre de :

* importer plusieurs fichiers CSV de prospects
* fusionner et dédupliquer les contacts
* savoir exactement qui a déjà été contacté
* ne jamais renvoyer un mail de présentation à la même personne
* gérer plusieurs campagnes de prospection
* envoyer automatiquement des mails personnalisés
* suivre les réponses reçues
* classer les réponses (positive, négative, neutre)
* proposer des relances
* être pilotée plus tard par OpenClaw

---

# Architecture générale

Le projet est séparé en trois parties :

```text
apps/
├─ web/     → interface React
└─ api/     → backend Python / FastAPI
```

L'application utilise :

* React + TypeScript + Vite pour l'interface
* FastAPI + SQLAlchemy pour le backend
* SQLite au début
* Gmail API pour envoyer et lire les mails
* Plus tard : OpenClaw branché sur les endpoints du backend

---

# Arborescence prévue

```text
App prospection/
├─ apps/
│  ├─ api/
│  │  ├─ app/
│  │  │  ├─ api/
│  │  │  ├─ core/
│  │  │  ├─ db/
│  │  │  ├─ models/
│  │  │  ├─ repositories/
│  │  │  ├─ schemas/
│  │  │  ├─ services/
│  │  │  └─ utils/
│  │  └─ tests/
│  └─ web/
│     └─ src/
├─ data/
│  ├─ imports/
│  ├─ exports/
│  └─ app.db
├─ docs/
├─ scripts/
├─ packages/
└─ README.md
```

---

# Comptes mail utilisés

Deux boîtes mail sont utilisées pour répartir les envois et éviter les limites / le spam.

## Boîte 1

* Adresse : `maxime.farre8@gmail.com`
* Utilisation : envois secondaires, récupération historique, secours

## Boîte 2

* Adresse : `maxime@maxime-farre.xyz`
* Utilisation : envois principaux et image professionnelle
* Cette adresse est connectée à Gmail

Les deux boîtes doivent être configurées dans Gmail avec SMTP + Gmail API.

---

# Règles importantes

1. Un contact est unique principalement grâce à son email.
2. Si deux lignes ont le même email, elles représentent le même contact.
3. Si aucun email n'existe, on tente une déduplication avec :

   * prénom
   * nom
   * entreprise
4. Un mail de présentation ne peut jamais être envoyé deux fois au même contact.
5. Si un contact a répondu, aucune relance automatique n'est envoyée.
6. Si une adresse rebondit ou est invalide, elle est bloquée.
7. Toutes les actions importantes doivent être enregistrées.

---

# Base de données prévue

## Table contacts

Contient les informations de base :

* prénom
* nom
* email
* entreprise
* poste
* source
* lien LinkedIn
* notes

## Table campaign_states

Contient l'état du contact dans une campagne :

* premier mail envoyé ou non
* relance 1 envoyée ou non
* relance 2 envoyée ou non
* réponse reçue
* sentiment de la réponse
* contact bloqué

## Table messages

Historique détaillé de tous les mails envoyés.

## Table replies

Historique détaillé des réponses reçues.

## Table imports

Historique des CSV importés.

---

# Scripts à développer

Tous les scripts devront être placés dans :

```text
apps/api/app/services/
```

ou dans :

```text
scripts/
```

pour les scripts manuels.

---

# 1. Script d'import des CSV

Fichier prévu :

```text
apps/api/app/services/csv_import_service.py
```

Fonction :

* lire plusieurs fichiers CSV
* détecter les colonnes
* normaliser les données
* enregistrer les contacts dans la base
* ignorer les doublons

Entrées possibles :

* prénom
* nom
* email
* entreprise
* poste
* lien LinkedIn

---

# 2. Script de déduplication

Fichier prévu :

```text
apps/api/app/services/dedupe_service.py
```

Fonction :

* fusionner les doublons
* détecter les contacts déjà connus
* marquer les cas ambigus

---

# 3. Script pour récupérer tous les contacts déjà contactés

Fichier prévu :

```text
apps/api/app/services/gmail_sent_contacts_service.py
```

Objectif :

Parcourir les mails envoyés dans Gmail et récupérer la liste de tous les destinataires déjà contactés.

Le script doit :

* se connecter aux deux comptes Gmail
* lire tous les mails envoyés (`in:sent`)
* récupérer les champs `To` et `Cc`
* fusionner les emails uniques
* stocker le résultat dans la base de données
* marquer automatiquement les contacts déjà contactés

Sortie prévue :

```text
email | dernière date | nombre de mails envoyés | boîte utilisée
```

Ce script est essentiel avant toute campagne afin d'éviter d'envoyer deux fois le même mail à la même personne.

---

# 4. Script de préparation des campagnes

Fichier prévu :

```text
apps/api/app/services/campaign_prepare_service.py
```

Fonction :

* récupérer les contacts éligibles
* exclure les contacts déjà contactés
* choisir le template adapté
* créer une file d'attente d'envoi

---

# 5. Script de rendu des templates

Fichier prévu :

```text
apps/api/app/services/mail_render_service.py
```

Fonction :

* prendre un template
* remplacer les variables
* générer le sujet
* générer le corps du mail

Variables possibles :

* prénom
* nom
* entreprise
* poste
* campagne

---

# 6. Script d'envoi des mails

Fichier prévu :

```text
apps/api/app/services/mail_send_service.py
```

Fonction :

* envoyer les mails automatiquement
* choisir la bonne boîte mail
* respecter une limite quotidienne
* enregistrer le résultat dans la base

Règles prévues :

* 20 à 30 mails / jour / boîte au début
* délai aléatoire entre chaque mail
* possibilité d'utiliser alternativement :

  * `maxime.farre8@gmail.com`
  * `maxime@maxime-farre.xyz`

---

# 7. Script de synchronisation des réponses Gmail

Fichier prévu :

```text
apps/api/app/services/gmail_sync_service.py
```

Fonction :

* lire les nouvelles réponses reçues
* retrouver le contact correspondant
* mettre à jour la base
* classer automatiquement la réponse

Classification prévue :

* positive
* négative
* neutre
* réponse automatique
* à vérifier

---

# 8. Script de classification des réponses

Fichier prévu :

```text
apps/api/app/services/reply_classification_service.py
```

Fonction :

* analyser le texte de la réponse
* détecter si la réponse est positive ou négative
* proposer une action

Exemples :

* “Nous serions ravis d'échanger” → positif
* “Nous n'avons pas de besoin actuellement” → négatif
* “Merci, je transfère à mon collègue” → neutre

---

# 9. Script de relance

Fichier prévu :

```text
apps/api/app/services/followup_service.py
```

Fonction :

* trouver les contacts sans réponse
* vérifier le délai depuis le premier mail
* préparer une relance
* ne jamais dépasser le nombre maximum de relances

---

# Templates prévus

Dossier :

```text
templates/
```

Templates prévus :

* intro_rh_asset_management.txt
* intro_private_equity.txt
* intro_family_office.txt
* intro_small_company.txt
* followup_1.txt
* followup_2.txt

---

# Interface prévue

L'application doit comporter une seule page avec une barre en haut :

* Dashboard
* Contacts
* Imports
* Campaigns
* Replies
* Settings

## Dashboard

Afficher :

* nombre de contacts
* nombre de mails envoyés
* nombre de réponses
* taux de réponse
* réponses positives
* réponses négatives

## Contacts

Tableau filtrable avec :

* prénom
* nom
* entreprise
* email
* statut
* dernier mail

## Imports

Permet d'importer des CSV.

## Campaigns

Permet de préparer puis envoyer une campagne.

## Replies

Permet de voir et classer les réponses.

---

# Connexion future avec OpenClaw

OpenClaw ne devra jamais modifier directement la base de données.

OpenClaw utilisera uniquement l'API.

Exemples d'actions possibles :

* importer automatiquement un CSV
* proposer une campagne
* générer des mails personnalisés
* analyser une réponse
* proposer un brouillon

Endpoints prévus :

```text
GET /contacts
POST /imports/csv
POST /campaigns/prepare
POST /campaigns/send
POST /replies/sync
```

---

# Lancement du projet

## Frontend

```text
cd apps/web
npm install
npm run dev
```

## Backend

```text
cd apps/api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

---

# Priorités de développement

Ordre conseillé :

1. Base SQLite + modèles
2. Import CSV
3. Déduplication
4. Dashboard + liste des contacts
5. Script de récupération des contacts déjà contactés depuis Gmail
6. Préparation des campagnes
7. Envoi des mails
8. Synchronisation des réponses
9. Connexion à OpenClaw
