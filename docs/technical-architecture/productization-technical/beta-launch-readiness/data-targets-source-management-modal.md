# Data targets — source management modal

**Status:** Complete on 2026-03-25 — implemented (`notion_oauth` enriched responses, `DataSourceManagementModal`, `/data-targets` overview).  
**Goal:** Beta user launch — simplify `/data-targets` by moving source discovery and target-selection details into a modal opened from the connected data source row.

**Related docs:** [Beta UI general polish](./beta-ui-general-polish.md), [Tech Deck: Admin Providers page](./tech-deck-admin-providers-page.md) (same "table + modal" management pattern), [Notion Database ID vs Data Source ID — Fix Plan](../../incident_investigations/notion-id-fix-plan-2026-03-16.md), [Tech Debt: Data source refresh duplicates targets / pollutes store](../../tech-debt/td-2026-03-23-datasource-refresh-duplicate-targets.md).

---

## 1. Summary

Today `DataTargetsPage` mixes two jobs:

1. Showing whether Notion is connected.
2. Managing the full discovered-source list and selecting sources as targets.

This spec keeps the page as the lightweight overview and moves the lower **Data targets** section into a new **source management modal** opened from the connected Notion row, most naturally via **Manage**.

It also closes an adjacent correctness issue: **refresh must update the same discovered source rows in place rather than creating duplicate-looking sources or targets because of unstable Notion identifiers**.

The redesigned flow:

1. `/data-targets` shows the page header plus the **Connected data sources** section.
2. The Notion row keeps **Refresh** and changes **Manage** from a route link into a modal trigger.
3. Beneath the row, show a compact callout such as: **"2 connected data sources refreshed Mar 25, 2026, 10:42 AM."**
4. Opening **Manage** shows a modal with all discovered sources, when each source was refreshed, whether it is tracked, and which properties are currently tracked for that source.
5. Users can still select untracked sources and click **Use selected** from inside the modal.

This keeps the page scannable while preserving the existing source-selection workflow.

---

## 2. Current baseline

### 2.1 Frontend

`notion_pipeliner_ui/src/routes/DataTargetsPage.tsx` currently:

- Loads `/management/connections`.
- If Notion is connected, loads `/management/connections/{id}/data-sources`.
- Renders a top **Connected data sources** section with **Refresh** and a **Manage** link to `/connections`.
- Renders a second **Data targets** section with:
  - discovered Notion databases,
  - tracked vs not tracked badges,
  - `last_properties_sync_at`,
  - checkboxes for untracked rows,
  - **Use selected** action.

### 2.2 Backend

Existing Notion management routes already cover the basic lifecycle:

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/management/connections` | List connector instances / auth status |
| `POST` | `/management/connections/{connection_id}/refresh-sources` | Discover and upsert external sources |
| `GET` | `/management/connections/{connection_id}/data-sources` | List discovered sources |
| `POST` | `/management/connections/{connection_id}/data-sources/select` | Create/select data targets from source ids |
| `GET` | `/management/data-targets/{target_id}/schema` | Fetch tracked target schema |

### 2.3 Important data-shape gaps

The current source payload is close, but not enough for the desired modal:

- It includes **tracked / not tracked** and **`last_properties_sync_at`**.
- It does **not** serialize a source-level **"refreshed at"** timestamp even though `connector_external_sources` stores refresh timing (`last_seen_at`, `updated_at`).
- It does **not** include the **properties currently tracked** for the source.

That means the modal needs an enriched source-management contract, not just a visual rewrite.

### 2.4 Identity / refresh correctness gap

The redesign should explicitly preserve one stable identity per logical Notion source.

Observed failure mode from prior debugging:

- refresh can appear to add new sources instead of updating existing ones,
- selection can then create additional targets because the source id changed,
- the user experiences this as "refresh duplicated my data sources."

The critical rule is:

- **the stored source identity must be the canonical Notion `data_source_id`, not a transient search result shape or a display-name match**

Related nuance:

- Notion search results may surface `object=database` or `object=data_source`
- `database.id` and `data_source.id` are **not interchangeable**
- downstream target selection, schema sync, and page creation all need a stable data-source handle

The modal work should therefore include a hard identity contract, not just new UI.

---

## 3. Target UX

### 3.1 `/data-targets` page after redesign

Keep:

- Page header and current top-level framing.
- Connected Notion row with status badge, workspace/account label, **Refresh**, and **Manage**.

Remove from the page body:

- The entire lower **Data targets** section and table.
- The page-level **Use selected** button.

Add:

- A compact summary line/callout under the Notion row:
  - source count,
  - latest refresh time,
  - optional tracked count.

Suggested copy:

- **`2 connected data sources refreshed Mar 25, 2026, 10:42 AM.`**
- Optional secondary text: **`1 tracked, 1 available to add.`**

### 3.2 Manage modal

Open from the Notion row's **Manage** control.

Recommended modal structure:

1. **Header**
   - Title: **Manage data sources**
   - Subtitle with workspace/account label if available
   - Close button

2. **Summary strip**
   - Total discovered sources
   - Last refresh timestamp
   - Refresh button

3. **Source list**
   - One row/card per discovered source
   - Columns or stacked fields:
     - selection checkbox for untracked sources only,
     - source name,
     - tracking badge,
     - source refreshed at,
     - last properties sync,
     - tracked properties

4. **Footer actions**
   - **Use selected (N)** for currently selected untracked rows
   - Close / cancel

### 3.3 Per-source presentation

Each source should show:

- **Name**: `display_name`
- **Tracking status**:
  - **Tracked**
  - **Not tracked**
- **Refreshed**: when the source record was last refreshed from Notion
- **Last properties sync**: when the tracked schema was last synced into `target_schema_snapshots`
- **Tracked properties**:
  - visible list of property names,
  - optional type pill per property,
  - if there are many, show the first few plus **"+N more"**

For untracked sources:

- show **Not tracked yet** or **Track this source to start syncing properties**
- do not invent a tracked-properties list from raw Notion metadata in v1

This keeps the meaning precise: the UI is showing the properties the app is actually tracking, not every property that might exist upstream.

### 3.4 Accessibility / interaction

- Modal uses the existing dialog pattern (`role="dialog"`, `aria-modal="true"`, Escape to close, backdrop close only when not busy).
- **Refresh** inside the modal should preserve selection where possible for still-untracked rows.
- If the same Refresh action is available on the page and in the modal, both should use the same request + response shape so counts and timestamps stay consistent.

---

## 4. API / backend proposal

### 4.1 Recommendation

Keep the existing routes, but enrich the **list** and **refresh** responses so the page summary and the modal consume one shared source-management contract.

Recommended routes:

| Method | Route | Notes |
|--------|-------|-------|
| `GET` | `/management/connections/{connection_id}/data-sources` | Return enriched source-management payload |
| `POST` | `/management/connections/{connection_id}/refresh-sources` | Same payload shape after refresh |
| `POST` | `/management/connections/{connection_id}/data-sources/select` | Keep existing create/select semantics |

### 4.1.1 Identifier contract and idempotent refresh

This feature should codify the following invariants:

1. **Canonical source id**
   - `connector_external_sources.external_source_id` stores the Notion **`data_source_id`**
   - `data_targets.external_target_id` stores that same canonical **`data_source_id`**

2. **Optional diagnostic parent id**
   - keep or add a separate field for the parent database id when useful (`external_parent_id` today)
   - never use that parent id as the primary identity for upsert or selection

3. **Refresh behavior**
   - refresh is an **upsert by** `(owner_user_id, connector_instance_id, external_source_id)`
   - if the same Notion source is rediscovered, update display metadata, accessibility, refresh timestamps, and tracked-property metadata in place
   - refresh alone must **not** create a new logical source or a new target

4. **Selection behavior**
   - selecting a source should reuse the canonical `external_source_id`
   - if a target already exists for that canonical id, selection updates sync state and returns the existing target rather than materializing a second one

5. **No display-name identity**
   - `display_name` may help map bootstrap targets like `target_locations`, but it must never be the uniqueness key for discovered sources

Implementation note:

- `NotionOAuthService.refresh_sources()` already attempts to resolve search results to a `data_source_id`; this behavior should be treated as the required source-of-truth contract and verified with tests so it does not regress.

### 4.2 Proposed response shape

```json
{
  "summary": {
    "totalSources": 2,
    "trackedSources": 1,
    "untrackedSources": 1,
    "lastRefreshedAt": "2026-03-25T17:42:00+00:00"
  },
  "sources": [
    {
      "external_source_id": "abc123",
      "display_name": "Locations",
      "is_accessible": true,
      "is_tracked": true,
      "source_refreshed_at": "2026-03-25T17:42:00+00:00",
      "last_properties_sync_at": "2026-03-25T17:43:20+00:00",
      "tracked_target_id": "target_locations",
      "tracked_properties": [
        { "name": "Name", "property_type": "title" },
        { "name": "Address", "property_type": "rich_text" },
        { "name": "Google Maps URL", "property_type": "url" }
      ]
    }
  ]
}
```

### 4.3 How to build it

Source-level refresh data should come from `connector_external_sources`:

- `source_refreshed_at` should serialize from `updated_at` or `last_seen_at`
- `summary.lastRefreshedAt` can be the max source refresh timestamp for that connection

Tracked-property data should come from the tracked target, if one exists:

1. Use the existing target lookup for the connection / owner.
2. Match by `external_target_id == external_source_id`.
3. Resolve the preferred tracked target using the same bootstrap preference already used elsewhere (`target_places_to_visit`, `target_locations`, then any per-source target).
4. Read the active schema snapshot from `target_schema_repository`.
5. Serialize a slim property list for the UI.

### 4.3.1 Duplicate prevention / migration expectations

Because this bug was previously observed, implementation should include explicit duplicate-handling rules:

- if historic rows exist for the same logical Notion source under conflicting identifiers, prefer the resolved **data source id** as canonical
- merge or backfill old rows before trusting modal counts for UX copy
- ensure repeated refreshes against an unchanged Notion workspace do not increase:
  - discovered-source row count,
  - tracked-target row count,
  - apparent available-to-add count

If a one-time cleanup is needed, it should be performed before or alongside the modal rollout so the new UI does not surface polluted legacy rows.

### 4.4 Why enrich instead of adding a separate modal endpoint

- The page summary and modal stay consistent after a single refresh.
- Fewer frontend code paths to keep in sync.
- Beta source counts are small enough that returning tracked property summaries with the list should be acceptable.

If payload size grows later, a v2 split into **summary list** + **per-source detail** is still possible.

---

## 5. Frontend proposal (`notion_pipeliner_ui`)

| Piece | Action |
|-------|--------|
| `DataTargetsPage.tsx` | Remove the lower section; keep overview + summary callout; replace `/connections` link with modal open state |
| New `DataSourceManagementModal` component | Render modal, fetch/manage sources, selection, refresh, tracked-properties display |
| `api.ts` | Extend `NotionDataSource` and refresh/list response types with summary + tracked property fields |
| `App.css` | Add modal/list styles only as needed; prefer reusing existing management modal/table tokens |
| Tests | Route/component smoke test for open/close, summary rendering, and `Use selected` in modal |

### 5.1 State flow

Recommended client state split:

- **Page state**
  - connection info
  - source summary for the callout
  - modal open / closed

- **Modal state**
  - detailed source list
  - selected untracked ids
  - loading / refresh / submit state

The page should not need to keep rendering the full source table once the modal is closed.

### 5.2 Reuse rules

- Keep `Refresh` behavior user-visible from the top row.
- Keep the existing **Use selected** semantics and backend endpoint.
- Keep `formatLastSync`-style local timestamp formatting, but distinguish:
  - **source refreshed at**
  - **properties last synced**

Those are related but not the same event.

---

## 6. Acceptance criteria

- [x] `/data-targets` no longer shows the lower standalone **Data targets** section.
- [x] The connected Notion row includes a **Manage** affordance that opens a modal instead of navigating away.
- [x] The page shows a compact summary of discovered sources and the most recent refresh timestamp.
- [x] The modal shows all discovered sources for the connection.
- [x] Each source row shows whether it is tracked, when it was refreshed, and which properties are currently tracked for that source.
- [x] Users can select untracked sources and click **Use selected** from inside the modal.
- [x] Refreshing source discovery updates both the modal contents and the page summary without requiring a full page reload.
- [x] Refreshing source discovery twice against an unchanged Notion workspace does not increase discovered-source count or create duplicate targets.
- [x] The canonical stored identifier for a discovered source is the Notion `data_source_id`, and refresh updates the existing row for that id in place.

---

## 7. Risks / notes

- A single external source may correspond to more than one target id today (bootstrap target plus per-source target). The response builder must choose one canonical tracked-target/schema source for property display.
- Historical rows created before the identifier contract was enforced may need cleanup or migration; otherwise the modal could faithfully display polluted data.
- `last_properties_sync_at` exists only for tracked targets with a schema snapshot; untracked rows should display a deliberate empty state, not misleading punctuation.
- If a source becomes inaccessible in Notion, keep showing it with a clear non-happy-path state rather than silently dropping it from the modal.

---

## 8. Out of scope (this iteration)

- Editing tracked properties from the modal.
- Showing the full raw Notion schema for untracked sources.
- Managing non-Notion source types.
- Reworking the standalone `/connections` page beyond removing the incorrect dependency on it from the Data Targets manage affordance.
