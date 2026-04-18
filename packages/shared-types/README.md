# shared-types

Package TypeScript contenant les types partagés entre le frontend (`apps/web`) et tout autre consommateur de l'API.

## Objectif

Centraliser les types correspondant aux schémas Pydantic du backend pour éviter la duplication et garantir la cohérence entre le contrat API et le frontend.

## Contenu prévu

```
shared-types/
├── src/
│   ├── contact.ts
│   ├── campaign.ts
│   ├── message.ts
│   ├── reply.ts
│   └── import-job.ts
├── package.json
└── tsconfig.json
```

## Usage prévu

```ts
import type { Contact, CampaignState } from '@app/shared-types'
```

## Note

Ce package n'est pas encore initialisé. Pour le moment, les types sont définis directement dans `apps/web/src/types/api.ts`. Ce package sera utile si un second consommateur de l'API est ajouté (ex : OpenClaw).
