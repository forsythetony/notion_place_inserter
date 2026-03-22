# Render: custom domains, HTTPS, redirects, and Notion OAuth

**Audience:** Anyone attaching purchased domains to the hosted **API** (Render Web Service), **static UI** (Render Static Site), and validating **Notion OAuth** plus **Supabase Auth** end-to-end.

**Related:** [Phase 1 deployment runbook](./productization-technical/phase-1-platform-migration/p1_pr08-deployment-runbook-and-render-exit.md), [Notion OAuth app setup](./productization-technical/phase-5-visual-editing/notion-oauth-app-setup-guide.md), `envs/env.template`.

---

## 1. What gets a public URL

| Surface | Render service type | Typical custom domain |
|--------|---------------------|------------------------|
| Backend API | Web Service (`notion-pipeliner-api` in `render.yaml`) | `api.example.com` |
| Frontend (Vite) | Static Site (`notion-pipeliner-ui` in the UI repo) | `app.example.com` or `www.example.com` |
| Worker | Background Worker | **No** public domain required (no inbound HTTP) |

Keep **API** and **UI** hostnames stable once users bookmark them or OAuth redirect URIs are registered.

---

## 2. HTTPS

Render provisions **TLS certificates automatically** for custom domains attached to a service (after DNS verifies). You do **not** need to upload your own cert for the standard Render flow.

**Checklist**

- Use **`https://`** in every production URL you configure (Notion redirect URI, `FRONTEND_BASE_URL`, `CORS_ALLOWED_ORIGINS`, Supabase Auth URLs, `VITE_BASE_URL`).
- Wait until the domain shows **Verified** (or equivalent) in Render before relying on OAuth; browsers and Notion require HTTPS for the production callback.

---

## 3. Attach domains in Render

Exact clicks change over time; follow Render’s docs for **Custom domains** on your service. At a high level:

1. **API (Web Service)** — Dashboard → your API service → **Settings** → **Custom Domains** → add hostname (e.g. `api.example.com`).
2. **UI (Static Site)** — Same for the static site (e.g. `app.example.com`).
3. At your DNS provider, create the **CNAME** (or A/ALIAS if Render specifies) Render shows for each hostname. Propagation can take minutes to hours.
4. Confirm **SSL certificate** status is active on the service.

**Default `*.onrender.com` URLs** keep working in parallel until you remove them; for production you usually want env vars and integrations to point at the **canonical custom hostnames** only.

---

## 4. Redirects (apex vs `www`, canonical host)

**Problem:** You may own both `example.com` and `www.example.com` (or `app.` vs `www.`). Browsers treat them as different **origins** for CORS and OAuth.

**Recommended pattern**

- Pick **one canonical** hostname for the UI (e.g. `https://app.example.com`).
- Attach **only** that hostname to the static site **or** attach both and configure **HTTP redirects** so one always redirects to the other with **301** and the same path.

**Where to configure**

- **DNS provider:** Some providers offer “redirect” records from apex to `www` (or vice versa).
- **Render:** Use **Redirects / Rewrite** rules for the static site if your plan supports them, or redirect at the DNS/CDN layer.

**CORS and Supabase**

- Include **only** the exact `https://` origins you expect users to hit (comma-separated for `CORS_ALLOWED_ORIGINS`). If you allow both `https://app.example.com` and `https://www.example.com` without redirecting, list **both** or users on the “wrong” host will see CORS failures.

**SPA routing**

- The UI `render.yaml` already rewrites `/*` → `/index.html` for React Router. Custom domains do not change that behavior.

---

## 5. Environment variables to update (API + worker)

Set these in the shared **environment group** (or each service) so **API and worker** stay aligned. Worker does **not** need `CORS_*` for browser traffic, but it **does** need the same Notion and Supabase secrets as the API.

| Variable | Purpose |
|----------|---------|
| `BASE_URL` | Public base URL of the API (e.g. `https://api.example.com`). Used for operational consistency and scripts; set to the HTTPS API origin. |
| `CORS_ALLOWED_ORIGINS` | Comma-separated **exact** UI origins, e.g. `https://app.example.com`. Required for browser calls from the static site. |
| `NOTION_OAUTH_REDIRECT_URI` | Must match Notion’s **Redirect URIs** exactly — see §6. |
| `FRONTEND_BASE_URL` | Base URL of the UI for **post–OAuth redirects** (no trailing slash), e.g. `https://app.example.com`. |

After changing env vars, **redeploy** the API (and worker if you changed shared secrets). Render does not always pick up env changes without a deploy depending on how you apply them.

---

## 6. Notion integration (OAuth) updates

The backend callback route is:

`GET /auth/callback/notion`

So the **full redirect URI** you register in Notion is:

```text
https://<your-api-host>/auth/callback/notion
```

**Steps**

1. In [Notion Integrations](https://www.notion.so/my-integrations) → your integration → **OAuth domain & credentials** → **Redirect URIs**:
   - Add the **new** HTTPS URL above (e.g. `https://api.example.com/auth/callback/notion`).
   - If you still use the old `*.onrender.com` URL for a transition period, keep both until you migrate traffic.
   - **Save changes** in Notion.
2. In your backend env (same value as in Notion):
   - `NOTION_OAUTH_REDIRECT_URI=https://<your-api-host>/auth/callback/notion`
3. Set **`FRONTEND_BASE_URL`** to the **UI** origin where users should land after OAuth (e.g. `https://app.example.com`). The code builds paths like `/connections?connected=notion` from this base.

**Exact match rule:** Scheme, host, path, and absence of a trailing slash on the path must match between Notion’s list and `NOTION_OAUTH_REDIRECT_URI`. See troubleshooting in [notion-oauth-app-setup-guide.md](./productization-technical/phase-5-visual-editing/notion-oauth-app-setup-guide.md).

---

## 7. Frontend static site (Vite) rebuild

`VITE_*` variables are **baked in at build time**. After changing the API URL:

1. In Render **Static Site** → **Environment**, set  
   `VITE_BASE_URL=https://<your-api-host>`  
   (no trailing slash; same origin you use for `curl` and CORS).
2. **Trigger a new deploy** (clear build cache if needed) so `npm run build` picks up the new value.
3. Keep `VITE_SECRET`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY` consistent with backend `SECRET` and your Supabase project.

---

## 8. Supabase Auth (sign-in / sign-up redirects)

Hosted auth uses the **Supabase project dashboard**, not only `supabase/config.toml` (local).

In **Supabase Dashboard** → **Authentication** → **URL Configuration**:

- **Site URL** — Set to your **canonical UI origin** (e.g. `https://app.example.com`).
- **Redirect URLs** — Add the same origin and any paths your app uses for password recovery or email links (wildcards are supported per Supabase docs; prefer explicit URLs for beta).

If Site URL or redirect allow-list does not include the UI origin users actually use, **magic links and OAuth-style redirects** can fail after the domain cutover.

---

## 9. Verification checklist

1. **API health** — `curl -H "Authorization: $SECRET" "https://<api-host>/"` → 200.
2. **CORS** — Open browser devtools on the UI origin; confirm API calls succeed without CORS errors.
3. **Notion OAuth** — Sign in → **Connections** → **Connect Notion** → complete flow → land on `/connections` on the **HTTPS UI** host.
4. **Supabase Auth** — Sign out and sign in again on the new domain; confirm session works.
5. **Triggers** — If you document trigger URLs for users, update examples to use `https://<api-host>/triggers/...` as appropriate.

---

## 10. Rollback

- Revert DNS or point custom domains back to the previous target if needed.
- Restore prior env values (`VITE_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `NOTION_OAUTH_REDIRECT_URI`, `FRONTEND_BASE_URL`, Supabase Site URL) and redeploy.
- Leave old Notion redirect URIs in place until you are sure no clients use them.
