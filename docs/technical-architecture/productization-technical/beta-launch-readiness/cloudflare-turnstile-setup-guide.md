# Cloudflare Turnstile setup (Oleo beta waitlist)

**Purpose:** Walk through creating and configuring **Cloudflare Turnstile** so the marketing **`/waitlist`** page can render a challenge and the **FastAPI** backend can verify tokens for `POST /public/waitlist`.

**Related architecture:** [Public beta waitlist page and submission security](./public-beta-waitlist-submission-architecture.md).

**Official reference:** [Cloudflare Turnstile — Get started](https://developers.cloudflare.com/turnstile/get-started/) and [Widget management (dashboard)](https://developers.cloudflare.com/turnstile/get-started/widget-management/dashboard/).

---

## Turnstile is opt-in (default off)

**Current default:** Turnstile is **disabled** until you explicitly enable it. The waitlist still uses the **honeypot**, **in-memory rate limiting**, and **manual review** of `beta_waitlist_submissions`.

| Layer | Variable | When Turnstile is off |
|-------|----------|------------------------|
| API | `TURNSTILE_ENABLED` | Unset, `0`, or `false` — no token verification; `TURNSTILE_SECRET_KEY` not required. |
| API | `TURNSTILE_ENABLED=1` (or `true`/`yes`) | Requires `TURNSTILE_SECRET_KEY` and a valid `captchaToken` on each request. |
| UI | `VITE_TURNSTILE_ENABLED` | Must be `true` or `1` to show the widget; also set `VITE_TURNSTILE_SITE_KEY`. |

Code paths stay in the repo (`WaitlistPage`, `turnstile_verification.py`); flip the env flags when you are ready.

---

## What you need in our app (when enabling Turnstile)

| Role | Environment variable | Where it lives |
|------|---------------------|----------------|
| **Site key** (public) | `VITE_TURNSTILE_SITE_KEY` | `notion_pipeliner_ui` — baked in at **build** time (Render Static Site). |
| **Secret key** (private) | `TURNSTILE_SECRET_KEY` | `notion_place_inserter` API (Render Web Service) — **never** expose to the browser or commit to git. |

The frontend loads the widget via `@marsidev/react-turnstile` on `WaitlistPage`. The backend verifies tokens with **`POST https://challenges.cloudflare.com/turnstile/v0/siteverify`** (see `app/services/turnstile_verification.py`).

---

## 1. Cloudflare account

1. Sign in to the [Cloudflare dashboard](https://dash.cloudflare.com/).
2. Turnstile is available **without** moving the whole site to Cloudflare DNS; you only need a Cloudflare account to manage widgets.

---

## 2. Create a Turnstile widget

1. Open **Turnstile** from the dashboard sidebar (or go directly: **Security** → **Turnstile**, depending on dashboard layout).
2. Click **Add widget** (or **Add site** / **Create** — wording may vary).
3. Configure:
   - **Widget name** — e.g. `Oleo waitlist production` (helps you find it later).
   - **Hostname management** — add every host where the **marketing site** will run the widget, for example:
     - Production: `yourdomain.com`, `www.yourdomain.com`
     - Preview/staging hosts if you use them
     - For **local dev**, you can use [Cloudflare’s dummy sitekeys](#5-local-development-and-ci-test-keys) **or** add `localhost` and `127.0.0.1` under hostname allowlisting if your production widget policy allows it (see Cloudflare’s [Hostname management](https://developers.cloudflare.com/turnstile/additional-configuration/hostname-management/)).
   - **Widget mode** — typically **Managed** (Cloudflare decides when to show extra interaction). Non-interactive and invisible modes are also supported; our React widget passes `theme` and uses the default interactive behavior appropriate for your mode.

4. **Create** the widget.

---

## 3. Copy keys and wire environments

After creation, Cloudflare shows:

- **Site key** — public; safe in frontend bundles.
- **Secret key** — private; only on the API server.

### Production (Render or similar)

1. **Static UI** (`notion-pipeliner-ui` or equivalent):
   - Set **`VITE_TURNSTILE_SITE_KEY`** to the **site key**.
   - Redeploy so Vite embeds it in the build.

2. **API** (`notion-pipeliner-api`):
   - Set **`TURNSTILE_SECRET_KEY`** to the **secret key**.
   - Restart the web service.

If the site key and secret key are **not from the same widget**, verification will always fail.

### Local development

Use a **`.env`** in `notion_pipeliner_ui` with `VITE_TURNSTILE_SITE_KEY` and run the API with `TURNSTILE_SECRET_KEY` in `envs/local.env` or shell env. **Do not** commit real secrets.

---

## 4. Dummy (test) keys for automated testing

Cloudflare documents **dummy** sitekeys and secret keys so tests do not hit real challenges. See [Test your Turnstile implementation](https://developers.cloudflare.com/turnstile/troubleshooting/testing/).

**Always-passes pair (typical for success-path tests):**

| Kind | Value |
|------|--------|
| Sitekey | `1x00000000000000000000AA` |
| Secret | `1x0000000000000000000000000000000AA` |

**Important:** Production secret keys **reject** dummy tokens; dummy **secret** keys only validate dummy tokens. Use matching test pairs on both sides.

**Vitest** in this repo defines `VITE_TURNSTILE_SITE_KEY` in `vitest.config.ts` for component tests; keep that aligned with your test strategy.

---

## 5. Local development and CI test keys

From Cloudflare’s testing docs:

- Dummy sitekeys work on **`localhost`**, **`127.0.0.1`**, and other dev hostnames.
- **Production** widgets should not rely on localhost unless you explicitly allow those hostnames in the widget’s hostname list.

---

## 6. Operational checks

1. **Browser:** Open `/waitlist` — the Turnstile widget should load (no “missing captcha configuration” if `VITE_TURNSTILE_SITE_KEY` is set).
2. **Submit:** Complete the challenge and submit; the API should return **202** with `{"status":"accepted"}` when validation and DB succeed.
3. **Mismatch:** Wrong secret → **400** “Captcha verification failed” from the API.
4. **Hostname:** If the widget’s allowed hostnames do not include your deployed origin, the widget may fail to load or validate — adjust the widget’s hostname list in the Cloudflare dashboard.

---

## 7. Security and hygiene

- Rotate the **secret** in Cloudflare if it leaks; update `TURNSTILE_SECRET_KEY` on the API only.
- Never put the secret in `VITE_*` or client-side code.
- Turnstile analytics (traffic, solve rates) in the Cloudflare dashboard can help you tune modes or spot abuse.

---

## 8. Quick env checklist

| Check | |
|--------|---|
| Site key in **frontend** build env | `VITE_TURNSTILE_SITE_KEY` |
| Secret in **API** only | `TURNSTILE_SECRET_KEY` |
| CORS | Frontend origin allowed in API `CORS_ALLOWED_ORIGINS` (already required for `fetch` to `VITE_BASE_URL`) |
| Same widget | Site key + secret from the **same** Turnstile widget |

---

## Changelog

| Version | Date | Notes |
|---------|------|--------|
| 2 | 2026-03-24 | Documented opt-in flags (`TURNSTILE_ENABLED`, `VITE_TURNSTILE_ENABLED`); default off. |
| 1 | 2026-03-24 | Initial runbook for Oleo `/waitlist` + FastAPI verification. |
