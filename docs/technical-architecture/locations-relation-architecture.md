# Locations Relation Resolution Architecture

## Goal

When creating a new page in **Places to Visit**, resolve its relation to the **Locations** database in the same pipeline-driven way as other properties:

- Link to an existing matching `Locations` page when one is found.
- Create a new `Locations` page when no good match exists.
- Return the Notion relation payload for the `Location` (or similarly named) relation property.

This should reuse existing schema retrieval/caching patterns and introduce a dedicated `Locations` service abstraction.

## Requirements

### Functional

1. Resolve the Places-to-Locations relation during property pipeline execution.
2. Support two outcomes:
   - **match**: link to one existing location page.
   - **create**: create a location page, then link to it.
3. Allow hierarchical location relationships (for example: city -> state).
4. Provide service calls to fetch all available locations.

### Non-Functional

1. Reuse/abstract the existing Notion schema loading + parsing + caching flow currently used for Places to Visit.
2. Cache location page data for **30 minutes**.
3. Keep behavior observable with structured logs and explicit decision metadata.

## Current State (Relevant)

- `NotionService` wraps API access and uses `SchemaCache` (lazy TTL cache) for DB schemas.
- Pipeline framework resolves properties in stage pipelines and custom pipelines.
- `PlacesService.create_place_from_query()` builds and runs `places_global_pipeline`.
- Relation properties are currently skipped by default fallback behavior.

## Proposed Design

## 1) Introduce `LocationsService`

Create a dedicated service for `Locations` DB page access and match/create behavior.

### Responsibilities

- Fetch all location pages from the `Locations` data source (with pagination).
- Normalize each location record into a lightweight domain model.
- Cache normalized location records for 30 minutes.
- Find best location match given extracted place/location context.
- Create new location pages when no acceptable match exists.
- Optionally resolve/attach parent location relation when applicable.

### Suggested public API

```python
class LocationsService:
    def get_all_locations(self, force_refresh: bool = False) -> list[LocationNode]: ...
    def find_best_match(self, candidate: LocationCandidate) -> MatchResult | None: ...
    def create_location(self, candidate: LocationCandidate, parent: LocationNode | None = None) -> LocationNode: ...
    def resolve_or_create(self, candidate: LocationCandidate) -> LocationResolution: ...
```

`LocationResolution` should include:
- `location_page_id`
- `resolution_mode` (`matched` | `created`)
- `matched_score` (optional)
- `matched_by` (optional: exact_name, normalized_name, alias, etc.)
- `parent_page_id` (optional)

## 2) Reuse/Abstract Schema Caching Pattern

Keep schema caching as the source of truth for database structures, but avoid duplicating logic:

- Continue using `NotionService.get_database_schema("Locations")`.
- If needed, extract a shared cache primitive for record lists (parallel to `SchemaCache`) so locations list cache follows the same lazy TTL semantics.

### New cache component (recommended)

```python
class LocationIndexCache:
    # lazy TTL cache; default ttl_seconds=1800
    def get(self) -> list[LocationNode]: ...
    def invalidate(self) -> None: ...
```

This mirrors current cache behavior:
- stale-on-read refresh
- lock-guarded state
- fetch outside lock

## 3) Add Relation Property Pipeline

Add a custom property pipeline for the relation field in Places to Visit (example name: `Location`).

### Pipeline shape

1. `BuildLocationCandidateStep`
   - Build `LocationCandidate` from `GOOGLE_PLACE` and/or query context.
   - Candidate fields may include:
     - `display_name` (city/neighborhood/locality)
     - `state_or_region`
     - `country`
     - `google_place_id` (if useful as stable key metadata)
2. `ResolveLocationRelationStep`
   - Calls `LocationsService.resolve_or_create(candidate)`.
   - Records resolution metadata in pipeline context for logs/debug.
3. `FormatLocationRelationForNotionStep`
   - Output Notion relation payload:
   - `{"relation": [{"id": "<location_page_id>"}]}`

### Registration

- Register pipeline in `custom_pipelines` registry mapped to the relation property name for Places to Visit.
- This overrides default skip behavior for this specific relation property only.

## 4) Parent Location Handling

Locations may reference a parent location (city in state, neighborhood in city).

### Data model expectation

`Locations` DB should include a self-relation property, e.g. `Parent Location`.

### Resolution behavior

When creating a new location:
1. Attempt to resolve parent from candidate context (state/region/country).
2. If parent exists, include self-relation on create.
3. If parent does not exist:
   - either create parent first (if confidence is high), or
   - create child without parent and log deferred-parent resolution.

Prefer conservative create behavior to avoid noisy hierarchy mistakes.

## 5) Matching Strategy

Use deterministic matching first; keep AI-assisted fallback optional.

### Recommended order

1. Exact normalized name + same higher-level context (state/country)
2. Alias map / alternate names (if modeled)
3. Case-insensitive name-only fallback
4. Optional AI tie-break when multiple close candidates exist

Introduce a confidence threshold:
- if confidence >= threshold -> match
- else -> create

## 6) Logging and Observability

Emit structured events during relation resolution:

- `location_relation_resolution_started`
- `location_relation_matched`
- `location_relation_created`
- `location_relation_resolution_failed`

Include metadata:
- `run_id`, `property_name`, `candidate_name`
- `resolution_mode`, `match_score`, `matched_page_id`, `created_page_id`
- cache info (`locations_cache_hit`, `locations_cache_age_s`)

## 7) Configuration

Add environment variables:

- `LOCATIONS_CACHE_TTL_SECONDS=1800`
- `LOCATION_MATCH_MIN_CONFIDENCE=0.85`
- `LOCATION_RESOLUTION_CREATE_PARENT=0|1` (optional)

Document defaults in `envs/env.template`.

## 8) Failure Semantics

Pipeline step failure policy for relation resolution:

- If location relation is required for DB integrity: propagate failure.
- If optional: skip property and continue, with warning log + skip reason in context.

Recommendation: start as optional in early rollout, then tighten once confidence is validated.

## 9) Implementation Plan

1. Create `app/services/locations_service.py`.
2. Add location list cache helper (`app/services/location_index_cache.py`) or equivalent internal cache in service.
3. Add custom pipeline for Places relation property (new file under `app/custom_pipelines/`).
4. Add pipeline steps under `app/pipeline_lib/steps/` for candidate build, resolve/create, format relation.
5. Register pipeline in `CUSTOM_PIPELINE_REGISTRY`.
6. Add tests:
   - match existing location
   - create when no match
   - parent attach behavior
   - cache TTL behavior (30 min)
   - fallback/error behavior
7. Update docs and local testing plan.

## 10) Example End-to-End Flow

1. `/locations` request starts and runs Places global pipeline.
2. Research stage populates normalized place context.
3. Property stage runs `LocationRelationPipeline`.
4. Pipeline builds candidate: `Minneapolis`, parent hint `Minnesota`.
5. `LocationsService` checks cached location index:
   - if `Minneapolis` exists under `Minnesota`: returns matched ID.
   - otherwise creates `Minneapolis` (and links to `Minnesota` if found).
6. Relation formatter returns Notion payload for `Location`.
7. Page create call writes Places page with linked location relation.

## Implementation Status

- [x] `LocationService` in `app/services/location_service.py`
- [x] `LocationIndexCache` in `app/services/location_index_cache.py` (30-min TTL)
- [x] Domain models: `LocationNode`, `LocationCandidate`, `LocationResolution` in `app/models/location.py`
- [x] `LocationRelationPipeline` and steps in `app/custom_pipelines/location_relation.py`, `app/pipeline_lib/steps/location_relation.py`
- [x] Registry: `Location`, `Locations` mapped to `LocationRelationPipeline`
- [x] Property stage: custom pipelines for relation properties override default skip
- [x] `PlacesService` injects `_location_service` into pipeline context
- [x] Env vars: `LOCATIONS_CACHE_TTL_SECONDS`, `LOCATION_MATCH_MIN_CONFIDENCE`, `LOCATION_RELATION_REQUIRED`
- [x] Tests: `tests/test_location_service.py`, `tests/test_location_relation_pipeline.py`

## Open Questions

1. What is the exact relation property name in Places to Visit (`Location`, `Locations`, etc.)? — **Implemented for both.**
2. Should multiple location relations ever be allowed for one place?
3. Do we maintain aliases/synonyms in `Locations` DB schema now, or later?
4. Should parent auto-creation be enabled at launch or deferred? — **Deferred; parent is linked when existing location matches.**
