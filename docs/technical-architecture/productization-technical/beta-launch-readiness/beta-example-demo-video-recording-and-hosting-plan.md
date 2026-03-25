# Beta: example demo video — recording plan and hosting

**Status:** **In progress** · **Ready for review**  
**Audience:** Founder / whoever records; frontend deploy (Render env)  
**Related:** [Landing page — live demo video (“See it in action”)](./landing-page-live-demo-see-it-in-action-architecture.md) (UI, env vars, acceptance criteria) · [`notion_pipeliner_ui` `landingDemoConfig`](../../../../../notion_pipeliner_ui/src/lib/landingDemoConfig.ts) · [`VITE_LANDING_DEMO_*`](../../../../../notion_pipeliner_ui/.env.example)

---

## Purpose

Ship the **creative assets** behind the already-built **“See it in action”** block: one **authentic screen recording** of Oleo, plus derived **preview loop** and **poster**, hosted at stable HTTPS URLs and wired via **`VITE_LANDING_DEMO_*`** for the beta landing experience.

This doc is the **run sheet** for recording and the **hosting decision** for upload and go-live.

---

## Deliverables (checklist)

| Asset | Role | Suggested spec |
|--------|------|----------------|
| **Master** | Full walkthrough in the modal (`<video controls>`) | **MP4**, **H.264**, AAC audio if narrated; 1080p or 1440p; frame rate 30 fps unless capture tooling defaults to 60 (either is fine if consistent). |
| **Preview loop** | Muted autoplay in the section | **3–10 s** clip from the **same session** (continuity); **MP4** or **WebM**, muted, small footprint; width capped (~960–1280 px) to control weight. |
| **Poster** (optional but recommended) | First paint + `prefers-reduced-motion` static frame | **WebP** or **JPEG**, same aspect as video, under ~200 KB if possible. |
| **Captions** (if there is speech) | Accessibility + clarity in noisy environments | **WebVTT** (`.vtt`); served at a URL → `VITE_LANDING_DEMO_CAPTIONS_VTT_URL`. |

**Naming (suggested):** `oleo-demo-master.mp4`, `oleo-demo-preview.mp4`, `oleo-demo-poster.webp`, `oleo-demo.vtt`.

---

## Pre-recording

- [ ] **Stable beta-shaped build** — Record against the same environment beta users will see (or clearly labeled staging with equivalent flows).
- [ ] **Account** — Clean session or a demo workspace; no sensitive customer data on screen.
- [ ] **Notion** — Test integration connected; a database/page visible where places land.
- [ ] **Display** — Browser zoom **100%**; OS “Increase contrast” off unless testing a11y; hide unrelated bookmarks bar if distracting.
- [ ] **Audio** (if voiceover) — Quiet room; **normalize** levels in export; optional noise reduction.
- [ ] **Cursor / clicks** — Move deliberately; pause on new screens so cuts and loops are easier.

---

## Content outline (aligned with architecture spec)

Target **total length ~3–8 minutes** unless product asks for longer; density beats filler.

1. **Intro (30–60 s)** — Name, role, why Oleo exists.
2. **Product tour (majority)** — Pipelines, triggers, runs, Notion-facing outcomes; pace for a first-time visitor.
3. **Live path** — One concrete story: **unstructured text → place extraction / resolution → records in Notion** (or the closest canonical “places” flow the beta supports). Label anything staged.
4. **Outro (15–30 s)** — Join waitlist / request access (match [public positioning](./public-product-name-and-positioning.md)).

**Preview loop:** Pick a **single visually clear moment** (e.g. text → run → Notion row appearing) with **no dependency on audio** (preview is muted).

---

## Post-production (minimal)

1. Trim head/tail silence; one pass of **loudness** normalization if narrated.
2. Export **master** to MP4 (H.264).
3. Export **preview** — short segment; re-encode for size (e.g. ffmpeg `-crf` / HandBrake “Web” preset).
4. Grab **poster** — frame export at a representative timestamp.
5. If narrated: draft **captions** (Descript, YouTube auto + edit, or manual) → export **WebVTT** timed to the master.

---

## Hosting options (comparison)

| Option | Pros | Cons |
|--------|------|------|
| **Static files in `notion_pipeliner_ui/public/`** | Zero new infra; same-origin; simplest `VITE_*` or relative paths | Large MP4s **bloat git and Render build artifacts**; every asset change = redeploy. |
| **Cloudflare R2** (public bucket + `https://` URL) | **Cheap storage**; **no egress to Cloudflare edge**; works with plain `<video src>`; fits custom domain later | One-time bucket + CORS + public access setup. |
| **AWS S3 + CloudFront** | Mature, global CDN | More moving parts and cost model; heavier ops for a solo beta. |
| **Vimeo / YouTube (unlisted)** | Built-in transcoding, optional captions UI | **Iframe or platform constraints** vs native `<video>` + `VITE_*` URLs; branding/ads policy; less ideal for the current modal pattern unless we switch to embed. |

---

## Preferred hosting (decision for beta)

**Primary recommendation: Cloudflare R2** — public bucket, object URLs (or a small **custom subdomain** e.g. `media.oleo.example`) referenced from:

- `VITE_LANDING_DEMO_FULL_VIDEO_URL`
- `VITE_LANDING_DEMO_PREVIEW_URL`
- `VITE_LANDING_DEMO_POSTER_URL`
- `VITE_LANDING_DEMO_CAPTIONS_VTT_URL`

**Rationale:** Keeps **large binaries out of the frontend repo and deploy bundle**, stays compatible with the existing **absolute-URL env** pattern, and aligns well if DNS moves toward Cloudflare ([Namecheap migration runbook](../../namecheap-domain-migration-runbook.md)). **CORS:** allow `GET` from the production (and preview) site origin for `Range` requests if players need them.

**Fallback for fastest beta unblock:** put **preview + poster only** in `public/demo/` (small files) and host **only the master** on R2, or host **all** under `public/` **temporarily** if R2 is not set up yet—then migrate to R2 before scale traffic.

---

## Upload and finish (runbook)

1. **Create** R2 bucket (or use fallback above); enable **public read** for these objects or serve via **R2 custom domain**.
2. **Upload** master, preview, poster, and optional `.vtt` with **cache-friendly** paths (e.g. `/oleo/v1/demo-master.mp4`) so future replacements can use `/v2/` without breaking old links if needed.
3. **Verify** each URL in a **private browser window**: `curl -I` or load in `<video>`; confirm **HTTPS** and **Content-Type** (`video/mp4`, `text/vtt`, `image/webp`).
4. **Set Render (or local) env** for the static site — see [`notion_pipeliner_ui` README](../../../../../notion_pipeliner_ui/README.md) — keys: `VITE_LANDING_DEMO_*` (see `.env.example` in that repo).
5. **Redeploy** the frontend so Vite bakes the URLs at build time.
6. **Smoke test** `/` — preview loops; open modal; full video plays; reduced-motion path shows poster; captions if enabled.

---

## Revision log

| # | Date | Change |
|---|------|--------|
| 1 | 2026-03-24 | Initial plan: deliverables, recording outline, R2 as preferred host, upload runbook, link to live-demo architecture. |
