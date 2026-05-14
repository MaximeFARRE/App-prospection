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
