# Custom icon library architecture

**Status:** Complete (v1 implementation 2026-03-28)  
**Intent:** Define backend, storage, admin UI, and runtime wiring for uploading, hosting, cataloging, and searching a first-party icon library backed by Postgres metadata and Cloudflare R2 objects.  
**Related:** [Architecture: Icon and Cover Image Pipelines](./productization-technical/phase-3-yaml-backed-product-model/icon-cover-image-pipeline-architecture.md), [Binding picker — output surface metadata](./binding-picker-output-surface-metadata.md)

## 1. Summary

Add a first-party icon catalog so operators can upload and manage icons we control instead of depending only on third-party search results.

**V1 format scope:** uploads accept **SVG only** (`image/svg+xml`). Raster support can be a later extension.

**V1 archive / removal:** **Postgres** rows are retained with `status = archived` (audit, job history). The **R2 object is deleted** so old public URLs no longer serve the file.

The design has five core parts:

1. **Cloudflare R2** stores the binary icon files.
2. **Postgres** stores icon metadata, tags, tag-association weights, and search-miss telemetry.
3. **Admin APIs + UI** let operators upload, bulk upload, edit, and browse the catalog.
4. **A new runtime step** searches the internal icon library by tag relevance and returns the best match.
5. **Miss logging** records unserved queries so the catalog can be expanded intentionally over time.

## 2. Goals

- Store icon metadata in Postgres, including title, dimensions, file type, color style, hosted URL, and timestamps.
- Model tags separately from icons so each icon-tag relationship can carry an explicit association strength.
- Host icon binaries in **Cloudflare R2** and expose stable public URLs (preferably through a custom media domain).
- Support backend search ranked primarily by tag strength, so searching `car` returns icons most strongly associated with `car`.
- Add a new pipeline step that searches this internal library and logs a miss when no result clears a configurable confidence threshold.
- Provide an admin interface for single upload, bulk upload, catalog browsing, metadata edits, and miss review.

## 3. Non-goals (v1)

- Replacing all external icon providers on day one. Existing Freepik-based behavior can remain as a legacy or fallback path during migration.
- Auto-tagging via embeddings or computer vision. V1 should rely on explicit operator-authored tags and weights.
- Tenant-specific icon libraries. V1 assumes one platform-managed shared catalog.
- Full CDN image transformation or raster derivation pipeline. V1 stores original uploaded files and minimal metadata only.

## 4. Current state and gap

Today the icon pipeline relies on **`step_template_search_icons`** and `SearchIconsHandler`, which call **Freepik** and return a single `image_url`. That is useful for fast experimentation but has several gaps:

- We do not control asset availability or provider rate limits.
- We cannot curate tags, brand fit, or visual consistency.
- We do not learn from misses in a structured way.
- Operators have no first-party UI for uploading and cataloging icons.

This document adds a durable internal catalog without breaking the existing icon/cover pipeline architecture.

## 5. Proposed architecture

### 5.1 High-level flow

1. Admin uploads one or more icon files.
2. API validates file type and extracts metadata.
3. Binary is written to **Cloudflare R2** under a stable object key.
4. Metadata rows are written to Postgres.
5. Operators edit tags and tag strengths in admin UI.
6. Runtime step searches Postgres metadata, ranks candidates by tag relevance, and returns the best icon URL.
7. If no result is strong enough, runtime logs a miss row for future catalog work.

### 5.2 Storage on Cloudflare R2

Use a dedicated bucket for platform media, for example:

- bucket: `oleo-media`
- prefix: `icons/`
- public base URL: `https://media.oleo.ai/icons/...` (preferred) or the R2 public object URL if a custom domain is not ready yet

Suggested object key shape:

`icons/{icon_asset_id}/original.{ext}`

Why this shape:

- Stable and human-debuggable.
- Asset id already exists in Postgres before or during finalization.
- Re-uploads can either replace the object intentionally or create a new asset row with a new id, depending on operator intent.

Postgres should store both:

- `storage_key` for operational control
- `public_url` for direct use by the runtime step and UI

**Archive lifecycle (v1):** When an operator archives an icon, the service sets `icon_assets.status` to `archived`, **deletes the object from R2** using `storage_key` (so the asset is not publicly retrievable), and **clears `public_url`** on the row so nothing implies a live URL. Retain `storage_key` (and the row) for audit. Search and runtime must exclude `archived` rows. **Reactivating** an archived row means uploading a new SVG again (new R2 `put`), which repopulates `storage_key`, `public_url`, and sets `status` back to `active` (or `draft` if you use a draft-first flow).

### 5.3 Postgres data model

Use explicit relational tables rather than a single JSON blob so tag ranking stays simple and indexable.

#### `icon_assets`

Primary metadata table for each hosted icon.

Suggested columns:

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | Stable asset id. |
| `title` | text not null | Operator-facing title. |
| `description` | text null | Optional internal notes. |
| `file_name` | text not null | Original uploaded name. |
| `file_type` | text not null | MIME type or normalized media type; v1 accepts `image/svg+xml` only. |
| `file_extension` | text not null | v1: `svg` only (schema leaves room for future formats). |
| `file_size_bytes` | bigint not null | For validation and debugging. |
| `width` | integer null | Null when unknown or not easily extracted. |
| `height` | integer null | Null when unknown or not easily extracted. |
| `color_style` | text not null | Check constrained to `light`, `dark`, `multicolor`. |
| `storage_provider` | text not null default `cloudflare_r2` | Explicit for future-proofing. |
| `storage_bucket` | text not null | R2 bucket name. |
| `storage_key` | text not null unique | Object key inside bucket; retained after R2 delete for audit. |
| `public_url` | text null unique (non-null values only) | URL returned to runtime/UI; **null when `archived`** after R2 delete. |
| `checksum_sha256` | text not null unique | Deduping and integrity. |
| `status` | text not null default `active` | `active`, `archived`, `draft`. |
| `created_by_user_id` | uuid null | Admin actor if available. |
| `created_at` | timestamptz not null default now() | Audit. |
| `updated_at` | timestamptz not null default now() | Audit. |

Notes:

- `title`, `dimensions`, `file_type`, `public_url` (when active), timestamps, and `color_style` satisfy the requested minimum metadata for live assets.
- Tags should **not** live as a simple array on this table in v1; the weighted join table is the source of truth.

#### `icon_tags`

Canonical tag vocabulary.

Suggested columns:

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | |
| `label` | text not null | Display form, e.g. `Car`. |
| `normalized_label` | text not null unique | Lowercased normalized search key, e.g. `car`. |
| `canonical_tag_id` | uuid null fk `icon_tags.id` | Optional aliasing; null for canonical tags. |
| `created_at` | timestamptz not null default now() | |
| `updated_at` | timestamptz not null default now() | |

`canonical_tag_id` lets us treat `cars`, `automobile`, or `vehicle-car` as aliases later without changing the search contract.

#### `icon_asset_tags`

Join table between icons and tags with explicit relevance weight.

Suggested columns:

| Column | Type | Notes |
|--------|------|-------|
| `icon_asset_id` | uuid fk `icon_assets.id` | |
| `icon_tag_id` | uuid fk `icon_tags.id` | |
| `association_strength` | numeric(5,4) not null | 0.0000 to 1.0000. |
| `is_primary` | boolean not null default false | Helpful for UI and curation. |
| `created_at` | timestamptz not null default now() | |
| `updated_at` | timestamptz not null default now() | |

Primary key:

`(icon_asset_id, icon_tag_id)`

Interpretation:

- `1.0` = icon is a direct, primary representation of the tag
- `0.7` = clearly relevant secondary concept
- `0.3` = weak contextual relation

This table is the basis for ranking.

#### `icon_search_misses`

Records search queries for which no icon met the minimum relevance threshold.

Suggested columns:

| Column | Type | Notes |
|--------|------|-------|
| `id` | uuid pk | |
| `normalized_query` | text not null | Query after normalization. |
| `raw_query` | text not null | Original query string. |
| `requested_color_style` | text null | `light`, `dark`, `multicolor`, or null. |
| `source` | text not null | `runtime_step`, `admin_preview`, etc. |
| `job_id` | text null | Optional context for curation (runtime app id, e.g. `loc_...`). |
| `job_run_id` | text null | Optional context for curation (runtime run id string). |
| `step_id` | text null | Pipeline step id if applicable. |
| `miss_count` | integer not null default 1 | Upserted aggregate count. |
| `first_seen_at` | timestamptz not null default now() | |
| `last_seen_at` | timestamptz not null default now() | |
| `example_context` | jsonb null | Small debugging/context payload. |
| `resolved` | boolean not null default false | Lets operators clear or hide addressed misses. |

Recommended uniqueness:

`unique (normalized_query, coalesce(requested_color_style, ''), source, coalesce(step_id, ''))`

Behavior:

- On repeated misses, update `miss_count` and `last_seen_at` instead of creating unlimited duplicates.
- Admin UI should sort unresolved misses by `miss_count desc, last_seen_at desc`.

#### Optional: `icon_ingest_batches`

For bulk upload traceability, add a small batch table if we want persistent audit and rerun visibility:

- `id`
- `uploaded_by_user_id`
- `source_type` (`zip_manifest`, `csv_only`, `single_upload`)
- `status`
- `item_count`
- `created_at`

This is optional for v1 but becomes useful quickly once bulk upload exists.

### 5.4 Indexing and search strategy

V1 search should be explicit and deterministic, not opaque semantic search.

Recommended indexes:

- `icon_assets(status, color_style, updated_at desc)`
- unique index on `icon_tags(normalized_label)`
- index on `icon_asset_tags(icon_tag_id, association_strength desc)`
- index on `icon_asset_tags(icon_asset_id)`
- optional trigram index on `icon_tags.normalized_label` if partial / fuzzy tag lookup is needed

### 5.5 Query normalization

Normalize search queries before lookup:

- lowercase
- trim whitespace
- collapse repeated spaces
- convert separators (`_`, `-`) to spaces
- optionally singularize simple plurals (`cars` -> `car`) if safe

V1 should not overreach into LLM-based normalization. Explicit tags and aliases are easier to reason about and debug.

### 5.6 Ranking model

Search should be ranked primarily by **tag association strength**.

For a normalized query:

1. Resolve matching tags by `normalized_label` and later aliases/canonical mapping.
2. Join `icon_asset_tags` to `icon_assets`.
3. Filter to `icon_assets.status = 'active'`.
4. If `colorStyle` is supplied, filter by exact `color_style`.
5. Compute score per icon.
6. Return results sorted by score descending, then `updated_at desc`, then `title`.

Suggested v1 score:

`score = max(association_strength * tag_match_weight)`

Where:

- exact canonical tag match: `tag_match_weight = 1.0`
- alias match: `0.95`
- prefix / fuzzy tag match if enabled: `0.75`

For multi-token queries later, use the sum of the top matched tag scores capped at `1.0` or another small bounded function.

### 5.7 Strong-match threshold and miss semantics

The runtime step should distinguish between:

- **search results exist**
- **a result is strong enough to use automatically**

Recommended step behavior:

- search endpoint can return ranked candidates even for weaker matches
- runtime step should only auto-select the first result if `score >= minimum_match_score`
- default `minimum_match_score` in v1: `0.80`

If no result clears that threshold:

- return `image_url: null`
- record or upsert a row in `icon_search_misses`
- include miss metadata in step logs

This prevents irrelevant icons from silently entering Notion pages.

## 6. API design

Use one shared backend service, for example `IconCatalogService`, with both admin routes and runtime callers using the same search logic.

### 6.1 Admin endpoints

All mutation routes should be admin-auth protected.

#### `POST /auth/admin/icons`

Create a single icon asset.

Recommended request shape:

- `multipart/form-data`
- file part: icon binary
- fields:
  - `title`
  - `description` (optional)
  - `colorStyle`
  - `tags` as JSON array of `{ label, associationStrength, isPrimary? }`

Behavior:

1. Validate file type and size.
2. Compute checksum.
3. Extract metadata.
4. Upload object to R2.
5. Upsert tags.
6. Insert `icon_assets` and `icon_asset_tags`.
7. Return created icon record.

#### `POST /auth/admin/icons/bulk`

Bulk upload many icons.

Recommended v1 input:

- `multipart/form-data`
- `archive` = zip file of assets
- `manifest` = JSON or CSV describing title, color style, and tags per file

Why zip + manifest:

- keeps uploads deterministic
- lets operators author tags and weights outside the browser
- supports a dry-run validation preview before ingest

Recommended response:

- per-file accepted/rejected results
- validation errors
- optional `batch_id`

#### `GET /auth/admin/icons`

Admin catalog browse endpoint with filters:

- `query`
- `tag`
- `colorStyle`
- `status`
- `limit`
- `cursor` or `offset`

#### `GET /auth/admin/icons/{icon_id}`

Single icon detail for edit screens.

#### `PATCH /auth/admin/icons/{icon_id}`

Edit metadata and tag associations.

Allow updates to:

- `title`
- `description`
- `colorStyle`
- `status`
- full replacement of tag association list

Treat tag edits as an authoritative replacement payload to avoid partial-update ambiguity.

When `status` transitions to **`archived`**, the handler must **delete the R2 object** and clear **`public_url`** as in §5.2. When transitioning from **`archived`** back to **`active`**, require a **new file upload** in the same request or a dedicated sub-route so R2 and `public_url` are repopulated before the row is active again.

#### `GET /auth/admin/icons/search`

Preview ranked search results using the same logic as runtime.

Query params:

- `query`
- `colorStyle` (optional)
- `limit`

Return:

- `items[]` with `iconId`, `title`, `publicUrl`, `colorStyle`, `score`, `matchedTags`

#### `GET /auth/admin/icons/misses`

List unresolved or recent misses for curation.

Filters:

- `resolved`
- `query`
- `source`

#### `PATCH /auth/admin/icons/misses/{miss_id}`

Mark miss as resolved or add operator notes later if desired.

### 6.2 Runtime search API / service contract

The worker should not call its own HTTP endpoint. It should use the same underlying service directly.

Suggested service method:

`search_icons(query: str, color_style: str | None = None, limit: int = 10) -> list[RankedIconMatch]`

Suggested match shape:

- `icon_asset_id`
- `title`
- `public_url`
- `color_style`
- `score`
- `matched_tags`

The admin preview route and runtime step can serialize this same shape.

## 7. Runtime step architecture

Add a new step template rather than mutating the existing Freepik step in place.

Suggested new template:

- id: `step_template_search_icon_library`
- display name: `Search Icon Library`
- input: `query`
- optional config:
  - `color_style_preference`
  - `minimum_match_score`
  - `record_miss`

Suggested output fields:

- `image_url`
- `icon_asset_id`
- `match_score`
- `matched_tags`

Why add a new step instead of reusing `step_template_search_icons`:

- avoids breaking current jobs that still expect Freepik semantics
- makes the new first-party behavior explicit in the product model
- allows side-by-side migration and testing

### 7.1 Runtime behavior

1. Resolve `query` input.
2. Normalize query (for logging); empty query skips search and returns **empty outputs** (no exception).
3. If the icon catalog service is not wired on the execution context, the step completes in a **degraded** state: `image_url` is `""`, with structured `error_detail` and warnings (see below).
4. Call `IconCatalogService.search_icons(...)`.
   - **Transient / infrastructure errors** (DB, network) are **not** raised to the job executor by default: the handler returns a **degraded** `StepExecutionResult` with `image_url: ""`, `error_message`, `error_detail`, and optional `warnings`, so the **pipeline continues** and the **worker does not retry the whole job** for that failure mode.
5. If there are no matches, or the top score is below `minimum_match_score`:
   - optionally upsert a miss row (`record_miss`)
   - return `image_url: ""` (empty string — matches the step output contract `type: string`).
6. If the top match clears the threshold:
   - return that hit (`public_url` as `image_url`, or `""` if the URL is missing).

**Structured results and observability**

- The handler returns `StepExecutionResult` (see `app/services/job_execution/runtime_types.py`). Outcomes:
  - **`success`**: normal hit or miss with string outputs.
  - **`degraded`**: soft failure with outputs (typically `image_url: ""`); the orchestrator persists `output_summary.step_outcome = structured_degraded`, `error_detail` (including `source: structured_step_result`), `error_summary`, and `processing_log` (including `WARNING:` lines). These fields are exposed on **pipeline run / admin run detail** APIs (`processingLog`, `outputSummary`, `errorDetail`) unchanged.
  - **`failed`**: explicit fatal outcome; `failure_policy` on the step instance applies the same way as a raised exception (e.g. `fail` aborts the job; `continue_with_default` fills template defaults).

- `continue_with_default` defaults for this template use `image_url: ""` in `default_outputs_for_step` when the executor applies recovery after an exception.

### 7.2 Relationship to existing icon/cover architecture

This step plugs into the existing pattern from [Architecture: Icon and Cover Image Pipelines](./productization-technical/phase-3-yaml-backed-product-model/icon-cover-image-pipeline-architecture.md):

1. `Optimize Input`
2. `Search Icon Library`
3. `Upload Image to Notion`
4. `Property Set` with `target_kind: page_metadata`, `target_field: icon_image`

No architectural change is required for `Upload Image to Notion` or `Property Set`.

## 8. Admin UI (`notion_pipeliner_ui`)

Add a new admin surface for icon library operations, preferably a dedicated route such as:

- `/admin/icons`

Recommended sections:

### 8.1 Catalog list

- searchable table or card grid
- thumbnail / preview
- title
- color style
- tags
- updated time
- status
- click-through to detail/edit

### 8.2 Single upload

- file picker / drag-drop
- metadata form
- tag editor with per-tag strength input
- immediate preview of extracted dimensions and detected type

### 8.3 Bulk upload

- zip + manifest upload
- dry-run validation summary before final import
- row-level error reporting
- optional downloadable error CSV later

### 8.4 Edit details

- rename title
- change color style
- archive (DB row kept, R2 object removed — link stops working) / reactivate (requires re-upload)
- edit tag weights
- inspect storage key; `public_url` empty when archived

### 8.5 Miss review

- unresolved miss queue
- sort by frequency and recency
- click a miss to prefill a search or upload flow
- mark resolved once a suitable icon has been added

## 9. Validation rules

- Allow only **SVG** in v1 (`image/svg+xml`, extension `svg`). Raster formats can be added later if needed.
- Enforce max file size per type.
- Require non-empty title.
- Require `color_style` in `light`, `dark`, `multicolor`.
- Require each `association_strength` to be within `[0, 1]`.
- Prevent duplicate tag labels after normalization within one asset payload.
- Prevent duplicate asset upload by `checksum_sha256` unless the operator explicitly confirms a duplicate.
- **Do not** hard-delete `icon_assets` rows in v1; use **`archived`** plus **R2 delete** so metadata remains for audit while binaries are not publicly accessible.

## 10. Observability and audit

Log structured events for:

- upload start / success / failure
- R2 put failures
- R2 delete on archive (success/failure)
- metadata extraction failures
- search requests and top score
- miss creation / miss upsert
- admin edits and archives

Recommended metrics:

- icon upload success/failure counts
- search request counts
- search hit rate above threshold
- miss count by normalized query
- top unresolved misses

## 11. Security and access

- Upload, bulk upload, edit, archive, and miss-resolution routes should be **admin only**.
- Search preview route can remain admin-only initially.
- Runtime service access stays in-process inside the backend/worker.
- Validate content type and file extension independently; do not trust browser MIME alone.
- Prefer R2 public-read via custom domain for simple delivery, but keep bucket write credentials server-side only.

## 12. Rollout plan

1. **Schema**
   - Add `icon_assets`, `icon_tags`, `icon_asset_tags`, `icon_search_misses` (and optionally `icon_ingest_batches`).
2. **Storage service**
   - Add R2 configuration and upload helper service.
3. **Backend admin APIs**
   - Single upload, bulk upload, list, detail, patch, search preview, miss list.
4. **Runtime**
   - Add `IconCatalogService` and `SearchIconLibraryHandler`.
   - Register `step_template_search_icon_library`.
5. **Frontend admin UI**
   - Add `/admin/icons` list, upload, bulk upload, edit, and misses views.
6. **Catalog migration**
   - Keep existing Freepik search step available while moving curated jobs to the new internal-library step.

## 13. Acceptance criteria

- Operators can upload a new icon and see its metadata and hosted URL in admin UI.
- Icons are stored in Cloudflare R2 and referenced from Postgres.
- Tags are modeled separately from icons and each icon-tag relationship stores an explicit strength.
- Searching `car` returns icons tagged `car`, ranked by association strength.
- A dedicated runtime step can search this internal library and return the best icon URL.
- When no icon clears the configured match threshold, the system records a searchable miss entry.
- Admin UI supports single upload, bulk upload, edit, browse, and miss review.

## 14. Open decisions

- **Alias modeling:** self-referential `canonical_tag_id` may be enough; separate alias table is only needed if alias metadata grows.
- **Bulk upload manifest format:** JSON is friendlier for nested tag weights; CSV is easier to edit manually. ZIP + JSON manifest is the best default.
- **Fallback behavior:** whether the new step should optionally fall back to Freepik when the internal library misses, or whether misses should stay explicit to force curation.
