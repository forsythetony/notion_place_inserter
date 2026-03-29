-- First-party icon library: metadata in Postgres, binaries in R2 (backend-only access).

-- ---------------------------------------------------------------------------
-- icon_assets
-- ---------------------------------------------------------------------------
CREATE TABLE public.icon_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  description text,
  file_name text NOT NULL,
  file_type text NOT NULL,
  file_extension text NOT NULL,
  file_size_bytes bigint NOT NULL,
  width integer,
  height integer,
  color_style text NOT NULL,
  storage_provider text NOT NULL DEFAULT 'cloudflare_r2',
  storage_bucket text NOT NULL,
  storage_key text NOT NULL,
  public_url text,
  checksum_sha256 text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  created_by_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT icon_assets_color_style_check CHECK (color_style IN ('light', 'dark', 'multicolor')),
  CONSTRAINT icon_assets_status_check CHECK (status IN ('active', 'archived', 'draft'))
);

CREATE UNIQUE INDEX icon_assets_storage_key_unique ON public.icon_assets (storage_key);
CREATE UNIQUE INDEX icon_assets_public_url_unique ON public.icon_assets (public_url) WHERE public_url IS NOT NULL;
CREATE UNIQUE INDEX icon_assets_checksum_active_unique ON public.icon_assets (checksum_sha256)
  WHERE status IN ('active', 'draft');

CREATE INDEX icon_assets_status_color_updated_idx ON public.icon_assets (status, color_style, updated_at DESC);

-- ---------------------------------------------------------------------------
-- icon_tags (canonical vocabulary + optional alias rows)
-- ---------------------------------------------------------------------------
CREATE TABLE public.icon_tags (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  label text NOT NULL,
  normalized_label text NOT NULL,
  canonical_tag_id uuid REFERENCES public.icon_tags (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX icon_tags_normalized_label_unique ON public.icon_tags (normalized_label);
CREATE INDEX icon_tags_canonical_idx ON public.icon_tags (canonical_tag_id);

-- ---------------------------------------------------------------------------
-- icon_asset_tags (weighted associations)
-- ---------------------------------------------------------------------------
CREATE TABLE public.icon_asset_tags (
  icon_asset_id uuid NOT NULL REFERENCES public.icon_assets (id) ON DELETE CASCADE,
  icon_tag_id uuid NOT NULL REFERENCES public.icon_tags (id) ON DELETE CASCADE,
  association_strength numeric(5, 4) NOT NULL,
  is_primary boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (icon_asset_id, icon_tag_id),
  CONSTRAINT icon_asset_tags_strength_check CHECK (
    association_strength >= 0 AND association_strength <= 1
  )
);

CREATE INDEX icon_asset_tags_tag_strength_idx ON public.icon_asset_tags (icon_tag_id, association_strength DESC);
CREATE INDEX icon_asset_tags_asset_idx ON public.icon_asset_tags (icon_asset_id);

-- ---------------------------------------------------------------------------
-- icon_search_misses
-- ---------------------------------------------------------------------------
CREATE TABLE public.icon_search_misses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  normalized_query text NOT NULL,
  raw_query text NOT NULL,
  requested_color_style text,
  source text NOT NULL,
  job_id uuid,
  job_run_id uuid,
  step_id text,
  miss_count integer NOT NULL DEFAULT 1,
  first_seen_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  example_context jsonb,
  resolved boolean NOT NULL DEFAULT false,
  CONSTRAINT icon_search_misses_color_style_check CHECK (
    requested_color_style IS NULL OR requested_color_style IN ('light', 'dark', 'multicolor')
  )
);

CREATE UNIQUE INDEX icon_search_misses_dedupe_idx ON public.icon_search_misses (
  normalized_query,
  coalesce(requested_color_style, ''),
  source,
  coalesce(step_id, '')
);

CREATE INDEX icon_search_misses_unresolved_idx ON public.icon_search_misses (resolved, miss_count DESC, last_seen_at DESC);

-- ---------------------------------------------------------------------------
-- RLS: backend service_role only (no policies)
-- ---------------------------------------------------------------------------
ALTER TABLE public.icon_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.icon_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.icon_asset_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.icon_search_misses ENABLE ROW LEVEL SECURITY;
