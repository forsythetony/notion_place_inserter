-- Backend-only table access: RLS on, no policies => deny for anon / JWT roles;
-- service_role (SUPABASE_SECRET_KEY) bypasses RLS. PostgREST direct access is blocked.

ALTER TABLE public.platform_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pipeline_run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.http_triggers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invitation_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.id_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ui_theme_presets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_ui_theme_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_cohorts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_rate_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.usage_provider_definitions ENABLE ROW LEVEL SECURITY;
