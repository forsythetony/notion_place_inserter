# Namecheap domain migration & Oleo rebrand runbook

**Audience:** Engineering / solo-dev executing the cutover from `*.onrender.com` hostnames to a custom Namecheap domain **and** renaming the product from "Notion Pipeliner" to **Oleo** across all surfaces.

**Related:** [Render: custom domains, HTTPS, redirects, Notion OAuth](./render-custom-domains-and-notion-oauth.md) (general reference), [Public product name and positioning](./productization-technical/beta-launch-readiness/public-product-name-and-positioning.md), [env.template](../../envs/env.template), [Notion OAuth app setup guide](./productization-technical/phase-5-visual-editing/notion-oauth-app-setup-guide.md).

---

## Scope

Two related changes executed together:

1. **Domain migration** — Point all public surfaces at a custom domain purchased from Namecheap (replacing `*.onrender.com` hostnames).
2. **Product rename** — Replace "Notion Pipeliner" / `notion-pipeliner-*` with **Oleo** / `oleo-*` across Render service names, the Notion integration, user-visible UI, and repo-level references.

Doing both at once minimizes the number of deploys and avoids an awkward state where the domain says "oleo" but the UI still says "Notion Pipeliner."

### Current state → target state

| Surface | Current | Target |
|---------|---------|--------|
| Frontend URL | `notion-pipeliner-ui.onrender.com` | `app.<yourdomain>` |
| Backend API URL | `notion-pipeliner-api.onrender.com` | `api.<yourdomain>` |
| Worker | *(no public URL)* | No URL change needed |
| Render service names | `notion-pipeliner-api`, `notion-pipeliner-ui`, `notion-pipeliner-worker` | `oleo-api`, `oleo-ui`, `oleo-worker` |
| Render env group | `notion-pipeliner-backend` | `oleo-backend` |
| Notion integration name | "Notion Pipeliner" (or current) | "Oleo" |
| UI brand / page title | "Notion Pipeliner" | "Oleo" |

> **Placeholder convention:** `<yourdomain>` stands for the Namecheap domain (e.g. `oleo.so`). Replace throughout before executing.

---

## Prerequisites

- [ ] Namecheap account with the domain purchased and DNS management accessible.
- [ ] Render dashboard access for both the API web service and the static site.
- [ ] Notion integration admin access at [notion.so/my-integrations](https://www.notion.so/my-integrations).
- [ ] Supabase project dashboard access (Authentication → URL Configuration).
- [ ] Ability to trigger deploys on both Render services (API + static site).
- [ ] Decision on final domain name (fill in `<yourdomain>` everywhere below).

---

## Phase 1 — Render service rename

Render allows renaming services without downtime. The old `*.onrender.com` hostname changes to match the new name, so do this **before** DNS setup (the CNAME targets will use the new names).

> **Caution:** Renaming a Render service changes its `*.onrender.com` URL immediately. Any bookmarks, env vars, or integrations pointing at the old `*.onrender.com` URL will break. Since we're about to replace those URLs with custom domains anyway, this is fine — but don't rename the services until you're ready to proceed through the rest of this runbook in one session.

### 1.1 Rename services in Render Dashboard

| Current name | New name |
|-------------|----------|
| `notion-pipeliner-api` | `oleo-api` |
| `notion-pipeliner-ui` | `oleo-ui` |
| `notion-pipeliner-worker` | `oleo-worker` |

For each: Dashboard → Service → **Settings** → **Name** → update → Save.

### 1.2 Rename the environment group

| Current name | New name |
|-------------|----------|
| `notion-pipeliner-backend` | `oleo-backend` |

Dashboard → **Environment Groups** → `notion-pipeliner-backend` → rename to `oleo-backend`. The link to services should persist.

### 1.3 Update `render.yaml` in both repos

**Backend** (`notion_place_inserter/render.yaml`):

| Line | Old | New |
|------|-----|-----|
| Service name (API) | `notion-pipeliner-api` | `oleo-api` |
| Service name (worker) | `notion-pipeliner-worker` | `oleo-worker` |
| `fromGroup` (both) | `notion-pipeliner-backend` | `oleo-backend` |
| Comment | "Notion Place Inserter" | "Oleo" |

**Frontend** (`notion_pipeliner_ui/render.yaml`):

| Line | Old | New |
|------|-----|-----|
| Service name | `notion-pipeliner-ui` | `oleo-ui` |
| Comment | "Notion Pipeliner UI" | "Oleo UI" |

---

## Phase 2 — DNS configuration at Namecheap

### 2.1 Decide on subdomain scheme

Recommended:

| Hostname | Points to |
|----------|-----------|
| `app.<yourdomain>` | Render Static Site (frontend) |
| `api.<yourdomain>` | Render Web Service (backend API) |

Alternative: use the bare apex for the frontend. The tradeoff is that apex domains require A/ALIAS records (Namecheap supports URL redirect for apex → subdomain, but CNAME on apex is non-standard). Subdomains with CNAME are simpler.

### 2.2 Get Render CNAME targets

1. **API:** Render Dashboard → `oleo-api` → Settings → Custom Domains → Add `api.<yourdomain>` → note the CNAME target.
2. **Frontend:** Render Dashboard → `oleo-ui` → Settings → Custom Domains → Add `app.<yourdomain>` → note the CNAME target.

### 2.3 Create DNS records in Namecheap

In **Namecheap → Domain List → Manage → Advanced DNS**:

| Type | Host | Value | TTL |
|------|------|-------|-----|
| CNAME | `api` | *(CNAME target from Render for API)* | Automatic |
| CNAME | `app` | *(CNAME target from Render for frontend)* | Automatic |

If you also want the bare apex to resolve:

| Type | Host | Value | TTL |
|------|------|-------|-----|
| URL Redirect (301) | `@` | `https://app.<yourdomain>/` | — |

> **Propagation:** CNAME records for subdomains typically propagate within a few minutes; worst case up to 48 hours.

### 2.4 Verify DNS + TLS

Wait for Render to show both domains as **Verified** with an active TLS certificate. Render provisions Let's Encrypt certs automatically once DNS resolves.

```bash
dig api.<yourdomain> CNAME +short
dig app.<yourdomain> CNAME +short

curl -sI https://api.<yourdomain>/health
curl -sI https://app.<yourdomain>/
```

---

## Phase 3 — Backend environment variables

Update these in the Render environment group (`oleo-backend`, renamed in Phase 1).

| Variable | Old value (example) | New value |
|----------|---------------------|-----------|
| `BASE_URL` | `https://notion-pipeliner-api.onrender.com` | `https://api.<yourdomain>` |
| `CORS_ALLOWED_ORIGINS` | `https://notion-pipeliner-ui.onrender.com` | `https://app.<yourdomain>` |
| `NOTION_OAUTH_REDIRECT_URI` | `https://notion-pipeliner-api.onrender.com/auth/callback/notion` | `https://api.<yourdomain>/auth/callback/notion` |
| `FRONTEND_BASE_URL` | `https://notion-pipeliner-ui.onrender.com` | `https://app.<yourdomain>` |

**Transition tip:** Temporarily include both origins in `CORS_ALLOWED_ORIGINS` (comma-separated) during the cutover window:

```
https://app.<yourdomain>,https://notion-pipeliner-ui.onrender.com
```

### Deploy API + worker

Trigger a **manual deploy** for both `oleo-api` and `oleo-worker`. Env-group changes are only picked up on deploy.

---

## Phase 4 — Notion integration update

### 4.1 Rename the integration

1. [Notion Integrations](https://www.notion.so/my-integrations) → your integration → **Basic information**.
2. Change the **name** from "Notion Pipeliner" (or whatever it currently reads) to **"Oleo"**.
3. Optionally update the **tagline/description** to match the new branding.
4. **Save.**

This name is what users see during the OAuth consent screen ("Allow **Oleo** to access your workspace?"), so it should match the product name.

### 4.2 Add the new redirect URI

1. Same integration → **OAuth domain & credentials** → **Redirect URIs**.
2. **Add:** `https://api.<yourdomain>/auth/callback/notion`
3. Keep the old `*.onrender.com` URI temporarily (Notion allows multiple).
4. **Save changes.**

Notion enforces exact-match on redirect URIs. The `NOTION_OAUTH_REDIRECT_URI` env var (set in Phase 3) must match character-for-character.

### 4.3 Remove the old redirect URI (later)

After verifying the OAuth flow end-to-end, return and remove the old URI.

---

## Phase 5 — Supabase Auth URL configuration

1. **Supabase Dashboard** → **Authentication** → **URL Configuration**.
2. Update:

| Setting | New value |
|---------|-----------|
| **Site URL** | `https://app.<yourdomain>` |
| **Redirect URLs** | Add `https://app.<yourdomain>/**` |

3. Keep old `*.onrender.com` entries during transition.
4. Remove them once confirmed stable.

---

## Phase 6 — Frontend: product rename in code

These changes land in the `notion_pipeliner_ui` repo and take effect on the next build/deploy.

### 6.1 User-visible UI text

| File | What to change |
|------|----------------|
| `index.html` | `<title>notion_pipeliner_ui</title>` → `<title>Oleo</title>` |
| `src/layouts/AppShell.tsx` | Sidebar brand: `"Notion Pipeliner"` → `"Oleo"` |

The landing page already uses "Oleo" throughout (`HeroPipelineSection.tsx`, `LandingPage.tsx`, etc.), so no changes needed there.

### 6.2 Package and build metadata

| File | What to change |
|------|----------------|
| `package.json` | `"name": "notion_pipeliner_ui"` → `"name": "oleo-ui"` |
| `package-lock.json` | Regenerated automatically after editing `package.json` — run `npm install` |

### 6.3 Repo-level docs and tooling

| File | What to change |
|------|----------------|
| `README.md` | `# Notion Pipeliner UI` → `# Oleo UI`; update `cd notion_pipeliner_ui` references and Render hostname examples |
| `Makefile` | `@echo "Notion Pipeliner UI"` → `@echo "Oleo UI"` |
| `.env.example` | Update `VITE_BASE_URL` example comment to use new domain |
| `styleguide/README.md` | References to "Notion Pipeliner" in design docs |
| `styleguide/design-principles.md` | Same |
| `styleguide/layout-and-navigation.md` | Same |

---

## Phase 7 — Frontend: domain update + rebuild

### 7.1 Update Render environment for the static site

In Render Dashboard → `oleo-ui` → **Environment**:

| Variable | New value |
|----------|-----------|
| `VITE_BASE_URL` | `https://api.<yourdomain>` |

`VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` do **not** change.

### 7.2 Trigger a rebuild

**Clear build cache** and trigger a new deploy: Render → `oleo-ui` → **Manual Deploy** → **Clear build cache & deploy**.

This picks up both the `VITE_BASE_URL` change and any code changes from Phase 6.

### 7.3 Verify the bundle

Open `https://app.<yourdomain>` and confirm:
- Page loads; title reads "Oleo".
- Sidebar brand reads "Oleo".
- Network requests target `https://api.<yourdomain>/...`.

---

## Phase 8 — Backend: product rename in code

These changes land in the `notion_place_inserter` repo.

### 8.1 Config and deployment files

| File | What to change |
|------|----------------|
| `render.yaml` | Service names + env group (already listed in Phase 1.3) |
| `envs/env.template` | Update example comments: `notion-pipeliner-api.onrender.com` → `api.<yourdomain>`, `notion-pipeliner-ui.onrender.com` → `app.<yourdomain>` |
| `envs/prod.env` | Update actual production values to new domain |
| `Makefile` (`test-cors` target) | Update `Origin` header from `https://notion-pipeliner-ui.onrender.com` to `https://app.<yourdomain>` |
| `README.md` | Replace all `notion-pipeliner-*` service/group names with `oleo-*`; update example URLs |

### 8.2 Source code and schema references

These are comments and metadata — not runtime-critical, but should be consistent:

| File | What to change |
|------|----------------|
| `schemas/ui_theme_config_v1.json` | `"$id"` URI: `notion-pipeliner.local` → `oleo.local` (or the real domain) |
| `app/services/ui_theme_service.py` | Comment: "aligned with notion_pipeliner_ui" → "aligned with oleo-ui" |
| `supabase/migrations/20260321120000_ui_theme_presets.sql` | Comment: same |

### 8.3 Cursor IDE configuration

Several `.cursor/` files reference the old name. These affect agent behavior, not production:

| File | What to change |
|------|----------------|
| `.cursor/rules/file-app-bug.mdc` | "Notion Pipeliner" → "Oleo" |
| `.cursor/rules/docs-placement.mdc` | `notion_pipeliner_ui` references |
| `.cursor/rules/service-restart-check.mdc` | `notion_pipeliner_ui/**` path references |
| `.cursor/rules/ui-style-guide-first.mdc` | Product name references |
| `.cursor/commands/file-bug.md` | Product name references |
| `.cursor/commands/expand-architecture.md` | Product name references |
| `.cursor/agents/eula-signup-blocker.md` | Product name references |

> **Note on directory names:** The repo directory `notion_pipeliner_ui/` and `notion_place_inserter/` are local filesystem names. Renaming them is optional and has cascading effects on IDE configs, workspace settings, and any scripts that reference the paths. Recommend deferring directory renames to avoid disruption — the product name visible to users is what matters.

---

## Phase 9 — Verification checklist

- [ ] **DNS resolution** — `dig` confirms both subdomains resolve.
- [ ] **TLS certificates** — Both HTTPS URLs return valid certs.
- [ ] **API health** — `curl -H "Authorization: $SECRET" "https://api.<yourdomain>/"` → 200.
- [ ] **Frontend loads** — `https://app.<yourdomain>` renders the SPA.
- [ ] **Page title** — Browser tab reads "Oleo".
- [ ] **Sidebar brand** — App shell shows "Oleo" (not "Notion Pipeliner").
- [ ] **CORS** — Browser devtools show API calls succeeding without CORS errors.
- [ ] **Supabase Auth** — Sign out and sign back in on the new domain.
- [ ] **Notion OAuth** — Connect Notion → consent screen shows "Oleo" → flow completes → lands on `/connections` on the new domain.
- [ ] **Worker** — Trigger a pipeline run; confirm the worker processes it.
- [ ] **Old URLs (transition)** — If kept active, confirm they still work.

---

## Phase 10 — Decommission old names

Once stable (give it a few days):

1. **Notion:** Remove old `*.onrender.com` redirect URI.
2. **Supabase:** Remove old `*.onrender.com` entries from Redirect URLs.
3. **CORS:** Remove old origin from `CORS_ALLOWED_ORIGINS`; redeploy API.
4. **Render:** Optionally remove old `*.onrender.com` hostname aliases (services keep running — you're just removing the public alias).
5. **DNS:** Confirm any redirect records (apex → `app.`) are working or clean up.

---

## Rollback

1. **DNS:** Remove CNAME records at Namecheap.
2. **Render services:** Can be renamed back to `notion-pipeliner-*` if needed.
3. **Env vars:** Revert `BASE_URL`, `CORS_ALLOWED_ORIGINS`, `NOTION_OAUTH_REDIRECT_URI`, `FRONTEND_BASE_URL` to old values; redeploy.
4. **Frontend:** Revert `VITE_BASE_URL` and code changes; clear cache and redeploy.
5. **Supabase:** Revert **Site URL**.
6. **Notion:** Old redirect URI should still be in the allow-list if you followed transition guidance.
7. **Code changes:** `git revert` the rename commits in both repos.

---

## Summary of all touch-points

| System | What changes | Where |
|--------|-------------|-------|
| **Render services** | Rename to `oleo-api`, `oleo-ui`, `oleo-worker` | Render Dashboard → Settings |
| **Render env group** | Rename to `oleo-backend` | Render Dashboard → Environment Groups |
| **Namecheap DNS** | CNAME records for `api.` and `app.` | Namecheap → Advanced DNS |
| **Render custom domains** | Attach `api.<yourdomain>` and `app.<yourdomain>` | Render Dashboard → Custom Domains |
| **Render env group vars** | `BASE_URL`, `CORS_ALLOWED_ORIGINS`, `NOTION_OAUTH_REDIRECT_URI`, `FRONTEND_BASE_URL` | `oleo-backend` env group |
| **Render static site env** | `VITE_BASE_URL` | `oleo-ui` → Environment |
| **Notion integration** | Rename to "Oleo" + add new redirect URI | [notion.so/my-integrations](https://www.notion.so/my-integrations) |
| **Supabase Auth** | Site URL + Redirect URLs | Supabase Dashboard → Authentication |
| **Frontend code** | `index.html` title, `AppShell.tsx` brand, `package.json` name | `notion_pipeliner_ui` repo |
| **Frontend docs** | `README.md`, `Makefile`, `.env.example`, `styleguide/` | `notion_pipeliner_ui` repo |
| **Backend config** | `render.yaml`, `env.template`, `prod.env`, `Makefile` | `notion_place_inserter` repo |
| **Backend code** | `ui_theme_config_v1.json` `$id`, comments in theme service + migration | `notion_place_inserter` repo |
| **IDE config** | `.cursor/rules/`, `.cursor/commands/`, `.cursor/agents/` | `notion_place_inserter` repo |
