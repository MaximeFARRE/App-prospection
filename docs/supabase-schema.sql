-- ============================================================
-- Supabase Schema — Base collaborative
-- Exécuter dans l'éditeur SQL du projet Supabase (en une fois).
-- ============================================================

-- ── TABLES ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.users (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email         TEXT UNIQUE NOT NULL,
  display_name  TEXT,
  credits       INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.contacts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_hash      TEXT UNIQUE NOT NULL,   -- SHA-256 normalisé, jamais d'email en clair
  email_encrypted TEXT,                   -- chiffrement AES ajouté en V2
  first_name      TEXT,
  last_name       TEXT,
  job_title       TEXT,
  company_name    TEXT,
  country         TEXT,
  linkedin_url    TEXT,
  email_status    TEXT DEFAULT 'unknown', -- 'unknown' | 'valid' | 'invalid'
  sex             TEXT,                    -- 'homme' | 'femme' | 'ambigu' | NULL
  quality_score   INT  DEFAULT 0,
  contact_count   INT  NOT NULL DEFAULT 0, -- nb de fois contacté (toute la base)
  is_visible      BOOLEAN DEFAULT FALSE,  -- passe à TRUE après validation serveur
  contributed_by  UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.contact_contributions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES public.users(id)    ON DELETE CASCADE,
  contact_id        UUID NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
  submitted_at      TIMESTAMPTZ DEFAULT now(),
  validation_status TEXT DEFAULT 'pending', -- 'pending' | 'accepted' | 'rejected'
  credits_awarded   INT  DEFAULT 0,
  UNIQUE(user_id, contact_id)
);

CREATE TABLE IF NOT EXISTS public.contact_unlocks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES public.users(id)    ON DELETE CASCADE,
  contact_id  UUID NOT NULL REFERENCES public.contacts(id) ON DELETE CASCADE,
  unlocked_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, contact_id)
);

CREATE TABLE IF NOT EXISTS public.contact_events (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email_hash  TEXT NOT NULL,
  event_type  TEXT NOT NULL CHECK (event_type IN ('contacted', 'replied', 'bounced')),
  user_id     UUID REFERENCES public.users(id),
  occurred_at TIMESTAMPTZ DEFAULT now()
);

-- ── INDEX ────────────────────────────────────────────────────

-- Lookup rapide pour la déduplication inter-utilisateurs
CREATE INDEX IF NOT EXISTS idx_contact_events_hash
  ON public.contact_events(email_hash);

-- Listing des déblocages par utilisateur
CREATE INDEX IF NOT EXISTS idx_unlocks_user
  ON public.contact_unlocks(user_id);

-- Historique des contributions par utilisateur
CREATE INDEX IF NOT EXISTS idx_contributions_user
  ON public.contact_contributions(user_id);

-- Filtrage sur is_visible lors du request_unlock
CREATE INDEX IF NOT EXISTS idx_contacts_visible
  ON public.contacts(is_visible)
  WHERE is_visible = TRUE;

-- ── ROW LEVEL SECURITY ───────────────────────────────────────

ALTER TABLE public.users                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contacts              ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_contributions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_unlocks       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.contact_events        ENABLE ROW LEVEL SECURITY;

-- contacts : visible uniquement si l'utilisateur courant l'a débloqué
CREATE POLICY "contacts_unlock_gate" ON public.contacts
  FOR SELECT USING (
    id IN (
      SELECT contact_id FROM public.contact_unlocks
      WHERE user_id = auth.uid()
    )
  );

-- contacts : tout utilisateur authentifié peut lire les contacts
-- Nécessaire pour que l'upsert avec RETURNING * fonctionne (PostgREST
-- exige une policy SELECT pour renvoyer la ligne insérée/mise à jour).
CREATE POLICY "contacts_select_authenticated" ON public.contacts
  FOR SELECT USING (auth.uid() IS NOT NULL);

-- contacts : tout utilisateur authentifié peut contribuer (insérer / mettre à jour)
CREATE POLICY "contacts_insert_authenticated" ON public.contacts
  FOR INSERT WITH CHECK (auth.uid() IS NOT NULL);

CREATE POLICY "contacts_update_authenticated" ON public.contacts
  FOR UPDATE USING (auth.uid() IS NOT NULL);

-- contributions : chacun voit et insère uniquement les siennes
CREATE POLICY "own_contributions_select" ON public.contact_contributions
  FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "own_contributions_insert" ON public.contact_contributions
  FOR INSERT WITH CHECK (user_id = auth.uid());

-- contact_events : lecture globale (déduplication cross-users), insertion propre
CREATE POLICY "events_read_all" ON public.contact_events
  FOR SELECT USING (true);

CREATE POLICY "events_insert_own" ON public.contact_events
  FOR INSERT WITH CHECK (user_id = auth.uid());

-- users : chacun voit et modifie uniquement son propre profil
CREATE POLICY "own_profile_insert" ON public.users
  FOR INSERT WITH CHECK (id = auth.uid());

CREATE POLICY "own_profile_select" ON public.users
  FOR SELECT USING (id = auth.uid());

CREATE POLICY "own_profile_update" ON public.users
  FOR UPDATE USING (id = auth.uid());

-- contact_unlocks : chacun voit les siens, peut en insérer
CREATE POLICY "own_unlocks_select" ON public.contact_unlocks
  FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "own_unlocks_insert" ON public.contact_unlocks
  FOR INSERT WITH CHECK (user_id = auth.uid());
