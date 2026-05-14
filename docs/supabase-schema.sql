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
  quality_score   INT  DEFAULT 0,
  is_visible      BOOLEAN DEFAULT FALSE,  -- passe à TRUE après validation serveur
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
