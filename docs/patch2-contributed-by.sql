-- ============================================================
-- PATCH 2 — à exécuter dans Supabase SQL Editor
-- ============================================================
-- 1. Ajout de la colonne contributed_by sur contacts
-- 2. Policy RLS INSERT sur users (nécessaire pour upsert_user)
-- 3. Policy RLS UPDATE sur users
-- ============================================================

-- ── 1. Colonne contributed_by ────────────────────────────────
-- Référence l'utilisateur Supabase qui a contribué le contact.
ALTER TABLE public.contacts
  ADD COLUMN IF NOT EXISTS contributed_by UUID
    REFERENCES auth.users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_contacts_contributed_by
  ON public.contacts(contributed_by);

-- ── 2. RLS sur public.users ──────────────────────────────────
-- Sans ces policies, upsert_user échoue avec 42501.

-- Tout utilisateur authentifié peut s'insérer lui-même
DROP POLICY IF EXISTS "own_profile_insert" ON public.users;
CREATE POLICY "own_profile_insert" ON public.users
  FOR INSERT WITH CHECK (id = auth.uid());

-- Chacun voit et modifie uniquement son propre profil (déjà créé
-- dans le schéma initial, mais on recrée pour garantir l'état)
DROP POLICY IF EXISTS "own_profile_select" ON public.users;
CREATE POLICY "own_profile_select" ON public.users
  FOR SELECT USING (id = auth.uid());

DROP POLICY IF EXISTS "own_profile_update" ON public.users;
CREATE POLICY "own_profile_update" ON public.users
  FOR UPDATE USING (id = auth.uid());

-- ── 3. Vérification ──────────────────────────────────────────
SELECT policyname, tablename, cmd
  FROM pg_policies
 WHERE tablename IN ('contacts', 'users')
 ORDER BY tablename, cmd;
