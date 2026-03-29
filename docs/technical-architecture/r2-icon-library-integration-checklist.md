# R2 integration checklist (icon library)

Short checklist to collect everything needed before **Cloudflare R2** works with the first-party icon library (uploads, public URLs, archive deletes). Full design: [custom-icon-library-architecture.md](./custom-icon-library-architecture.md).

## What the app expects

The backend uses **S3-compatible APIs** (`boto3`) against R2. All of these must be set **on the API and the worker** (same values):

| Env var | What to put | Notes |
|--------|--------------|--------|
| `R2_ENDPOINT_URL` | S3 API endpoint for your account | Format: `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` — from **R2** → **Overview** (or account subpath in dashboard URL). |
| `R2_ACCESS_KEY_ID` | Access key id | Create under **R2** → **Manage R2 API Tokens** (or account **API Tokens** with R2 read/write). Use an **S3-compatible** access key pair if you use “Create Account API token” with R2 permissions. |
| `R2_SECRET_ACCESS_KEY` | Secret for that key | Store only in secrets / env files — never commit. |
| `R2_BUCKET_NAME` | Bucket name | Create an **R2 bucket** (e.g. `oleo-media`). Must match the bucket you grant the token access to. |
| `R2_KEY_PREFIX` | Optional object key prefix | **Unset or empty** = objects at `icons/<uuid>/original.svg`. If set (e.g. `oleo` or `prod/icons`), uploads use `{prefix}/icons/<uuid>/original.svg`. Leading/trailing slashes are ignored (`/oleo/` → `oleo`). Stored in DB as the full `storage_key`; public URLs use the same path after `R2_PUBLIC_BASE_URL`. |
| `R2_PUBLIC_BASE_URL` | Origin used in **browser-facing URLs** | **No trailing slash.** The app builds `public_url` as `{R2_PUBLIC_BASE_URL}/{storage_key}` (e.g. `storage_key` = `icons/<uuid>/original.svg`, or with prefix `oleo/icons/<uuid>/original.svg`). |

If any of these are missing, the app logs `r2_media_storage_disabled` and **uploads / archive deletes** that need R2 will fail or be unavailable.

## Gather in Cloudflare (order that usually works)

1. **Account ID** — Dashboard sidebar or URL when viewing R2 (needed for `R2_ENDPOINT_URL`).
2. **Bucket** — R2 → **Create bucket** → note **exact name** → `R2_BUCKET_NAME`.
3. **S3 API credentials** — R2 → **Overview** / **Manage R2 API Tokens** → create token with **Object Read & Write** (and **Edit** permission on the bucket if scoped). Copy **Access Key ID** and **Secret Access Key** → `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`.
4. **Public URL strategy** (pick one):
   - **Custom domain** (recommended for production): Connect a subdomain (e.g. `media.yourdomain.com`) to R2 under the bucket’s **Settings** → **Public access** / **Custom Domains**, then set `R2_PUBLIC_BASE_URL=https://media.yourdomain.com` (or whatever path prefix you expose; the app appends `/{storage_key}`).
   - **R2.dev public bucket URL** (quick test): Enable **Public access** on the bucket and use the **r2.dev** subdomain Cloudflare shows, if you accept that hostname for asset URLs.

Confirm in a browser: after upload, `R2_PUBLIC_BASE_URL` + `/{storage_key}` should load when the object exists — e.g. `/icons/<id>/original.svg` with no prefix, or `/oleo/icons/<id>/original.svg` when `R2_KEY_PREFIX=oleo` (and return **404** after archive delete).

## Copy into your env

- Local: `envs/local.env` or project `.env` (see [env.template](../../envs/env.template)).
- Production: host secrets (e.g. Render **Environment**) for **both** API and worker services.

`R2_SECRET_ACCESS_KEY` is treated as sensitive in startup logs (masked) — see `app/env_bootstrap.py`.

## After values are set

1. Apply DB migration that creates icon tables (if not already): `icon_assets`, etc.
2. Restart **API** and **worker** so they load the new env and `boto3` can reach R2.
3. In **Admin** → **Icons** (`/admin/icons`), try a small SVG upload; confirm the returned `publicUrl` opens and matches your public URL strategy.

## Optional notes

- **CORS** is usually irrelevant for `<img src="...">` from Notion or the admin UI loading the image URL; if you ever load objects from browser **JavaScript** cross-origin, add CORS rules on the bucket.
- **Region** in code is fixed to `auto` for R2; no extra env.
- Icon **archive** deletes the object in R2 by `storage_key` and clears `public_url` in Postgres — old links should 404 even if the DB row remains.
