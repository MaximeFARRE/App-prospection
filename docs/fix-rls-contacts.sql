-- ============================================================
-- FIX RLS contacts — à exécuter dans Supabase SQL Editor
-- ============================================================
-- Ce script est idempotent : il supprime puis recrée toutes les
-- policies de la table contacts pour garantir l'état correct.

-- 1. Vérifier que RLS est activé
ALTER TABLE public.contacts ENABLE ROW LEVEL SECURITY;

-- 2. Supprimer les policies existantes (ignore si n'existent pas)
DROP POLICY IF EXISTS "contacts_unlock_gate"           ON public.contacts;
DROP POLICY IF EXISTS "contacts_select_authenticated"  ON public.contacts;
DROP POLICY IF EXISTS "contacts_insert_authenticated"  ON public.contacts;
DROP POLICY IF EXISTS "contacts_update_authenticated"  ON public.contacts;

-- 3. Recréer toutes les policies

-- Lecture : tout utilisateur authentifié peut lire les contacts
-- (nécessaire pour que l'upsert RETURNING * fonctionne)
CREATE POLICY "contacts_select_authenticated" ON public.contacts
  FOR SELECT USING (auth.uid() IS NOT NULL);

-- Insertion : tout utilisateur authentifié peut contribuer
CREATE POLICY "contacts_insert_authenticated" ON public.contacts
  FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);

-- Mise à jour : tout utilisateur authentifié peut mettre à jour
CREATE POLICY "contacts_update_authenticated" ON public.contacts
  FOR UPDATE USING (auth.uid() IS NOT NULL);

-- 4. Vérification
SELECT policyname, cmd, permissive, qual, with_check
  FROM pg_policies
 WHERE tablename = 'contacts';
