# Architecture Design: Dynamic Schema & Parallel Page/Property Pipelines

## Context

The application accepts unstructured text like `"stone arch bridge in minneapolis"` and uses AI + the Google Places API to gather structured data, then inserts a rich record into a Notion "Places to Visit" database.

Two architectural challenges need solving:

1. The Notion schema is mutable — properties and select options can change at any time in Notion — and the application needs to stay in sync without constant polling.
2. Each property on the Notion record may require its own resolution logic (API calls, AI inference, transformations). These should run in parallel and be easy to author, debug, and extend.

---

## 1. Dynamic Schema with TTL-Based Caching

### Problem

Today, `NotionService.initialize()` fetches the database schema once at startup and caches it forever. If a user adds a new property or select option in Notion, the app has no way to pick that up without a restart.

### Design

Introduce a `SchemaCache` that wraps the Notion schema retrieval behind a time-to-live (TTL) mechanism. On every request that needs the schema, the cache checks whether the data is stale. If it is, it re-fetches from Notion. If not, it returns the cached copy. This is **lazy invalidation** — no background polling, no timers, no threads.

```
┌────────────────────────────────┐
│         Incoming Request       │
└──────────────┬─────────────────┘
               │
               ▼
┌──────────────────────────────────┐
│        SchemaCache.get()         │
│                                  │
│  if now - last_fetched > ttl:    │
│      fetch from Notion API       │──► Notion API
│      update cache + timestamp    │
│  else:                           │
│      return cached schema        │
└──────────────────────────────────┘
```

### `SchemaCache` Class

```python
import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class CachedSchema:
    properties: dict
    data_source_id: str
    fetched_at: float


class SchemaCache:
    """Lazy TTL cache for Notion database schemas."""

    def __init__(self, notion_client, ttl_seconds: float = 300):
        self._client = notion_client
        self._ttl = ttl_seconds
        self._entries: dict[str, CachedSchema] = {}
        self._lock = Lock()

    def get(self, db_name: str) -> CachedSchema:
        with self._lock:
            entry = self._entries.get(db_name)
            if entry and (time.monotonic() - entry.fetched_at) < self._ttl:
                return entry

        # Fetch outside the lock to avoid blocking concurrent readers
        fresh = self._fetch(db_name)

        with self._lock:
            self._entries[db_name] = fresh
        return fresh

    def invalidate(self, db_name: str | None = None):
        """Force a refresh on next access. None = invalidate all."""
        with self._lock:
            if db_name:
                self._entries.pop(db_name, None)
            else:
                self._entries.clear()

    def _fetch(self, db_name: str) -> CachedSchema:
        # Implementation: retrieve database, extract properties
        # (mirrors current NotionService.initialize logic but per-DB)
        ...
```

### Key decisions

| Decision | Rationale |
|---|---|
| **Lazy (on-demand) invalidation** over polling | Simpler, no background threads, no wasted API calls when the app is idle. The cost is a single slow request every TTL window. |
| **TTL of 5 minutes (configurable)** | Balances freshness with API rate limits. Notion schemas don't change mid-conversation. |
| **Thread lock around cache reads/writes** | FastAPI runs sync route handlers in a threadpool. The lock prevents torn reads. Could use `asyncio.Lock` if routes go fully async. |
| **Schema stored as a dataclass** | `CachedSchema` is a plain data object — easy to inspect, serialize for debugging, and pass around. |

### How it changes `NotionService`

`NotionService` drops its `_schema_cache` dict and delegates to `SchemaCache`. The `initialize()` method becomes optional (for eagerly warming the cache at startup) rather than required. `get_schema()` becomes a pass-through to `SchemaCache.get()`.

```python
class NotionService:
    def __init__(self, api_key: str, schema_ttl: float = 300):
        self._client = Client(auth=api_key)
        self._cache = SchemaCache(self._client, ttl_seconds=schema_ttl)

    def get_schema(self, db_name: str) -> dict:
        return self._cache.get(db_name).properties

    def get_data_source_id(self, db_name: str) -> str:
        return self._cache.get(db_name).data_source_id
```

### Representing the schema as dataclasses

The raw Notion schema is a nested dict. To make it ergonomic in Python, parse it into typed dataclasses on cache-fill:

```python
from dataclasses import dataclass


@dataclass
class SelectOption:
    id: str
    name: str
    color: str


@dataclass
class PropertySchema:
    name: str
    type: str  # "title", "select", "rich_text", "url", etc.
    options: list[SelectOption] | None = None  # for select / multi_select


@dataclass
class DatabaseSchema:
    db_name: str
    data_source_id: str
    properties: dict[str, PropertySchema]
    fetched_at: float
```

A factory function parses the raw Notion API response into a `DatabaseSchema`:

```python
def parse_schema(db_name: str, data_source_id: str, raw_properties: dict) -> DatabaseSchema:
    props = {}
    for name, raw in raw_properties.items():
        prop_type = raw.get("type", "unknown")
        options = None
        if prop_type in ("select", "multi_select"):
            raw_opts = raw.get(prop_type, {}).get("options", [])
            options = [
                SelectOption(id=o["id"], name=o["name"], color=o.get("color", ""))
                for o in raw_opts
            ]
        props[name] = PropertySchema(name=name, type=prop_type, options=options)
    return DatabaseSchema(
        db_name=db_name,
        data_source_id=data_source_id,
        properties=props,
        fetched_at=time.monotonic(),
    )
```

This means the rest of the application never touches raw dicts for schema data. When the schema changes in Notion, the cache expires, the factory re-parses, and every consumer gets fresh `PropertySchema` objects with updated options — no restart needed.

---

## 2. Pipeline Abstraction Library

### Goal

Build a reusable internal library with one consistent execution model:

1. `GlobalPipeline` (top-level orchestrator, scoped to one database schema)
2. `Stage` (dependency boundary between sets of work)
3. `Pipeline` (work unit inside a stage)
4. `PipelineStep` (ordered operations inside a pipeline)

The current "gather research" behavior is not a framework primitive. It is an **application-level `Stage` implementation** that uses the same library abstractions as every other stage.

### Execution Semantics

- `GlobalPipeline` runs stages in declared order.
- Stages are **sequential by default**.
- A stage may declare `run_mode="parallel"` when independent and safe to overlap.
- Inside a `Pipeline`, steps run sequentially.
- Inside a parallel stage, pipelines are fanned out and joined before moving forward.

### Library Diagram (abstraction creation section)

```
┌───────────────────────────────────────────────────────────────┐
│                   pipeline_lib (framework)                    │
├───────────────────────────────────────────────────────────────┤
│ GlobalPipeline                                                │
│   - pipeline_id                                               │
│   - schema_binding                                            │
│   - stages() -> list[Stage]                                  │
│   - run(context)                                              │
├───────────────────────────────────────────────────────────────┤
│ Stage                                                         │
│   - stage_id                                                  │
│   - run_mode: "sequential" | "parallel" (default: sequential)│
│   - pipelines() -> list[Pipeline]                            │
│   - run(context)                                              │
├───────────────────────────────────────────────────────────────┤
│ Pipeline                                                      │
│   - pipeline_id                                               │
│   - steps() -> list[PipelineStep]                            │
│   - run(context)                                              │
├───────────────────────────────────────────────────────────────┤
│ PipelineStep                                                  │
│   - step_id                                                   │
│   - execute(context, current_value) -> current_value         │
└───────────────────────────────────────────────────────────────┘
```

### Logging and Orchestration Contract

Every emitted log should carry orchestration identity fields so execution is traceable end-to-end.

Required fields:
- `run_id` (single request correlation ID)
- `global_pipeline`
- `stage`
- `pipeline`
- `step` (when relevant)
- `event` (`start`, `success`, `failure`, `join_wait`, `join_complete`)
- `duration_ms`

Recommended orchestration events:
- Global pipeline started/completed/failed
- Stage scheduled/started/completed/failed
- Stage fan-out started and join completed
- Pipeline started/completed/failed
- Step started/completed/failed
- Context writes (`context_key`, payload summary)

Example log lines:

```python
logger.bind(
    run_id=run_id,
    global_pipeline="places_global_pipeline",
    stage="research",
    pipeline="query_to_google_cache",
    step="rewrite_query_with_claude",
).info("step_start")
```

```python
logger.bind(
    run_id=run_id,
    global_pipeline="places_global_pipeline",
    stage="property_resolution",
    event="join_complete",
    duration_ms=1840,
).info("stage_join_complete")
```

---

## 3. Places DB Implementation Using the Library

This section describes how the application consumes the abstractions to create new Places entries from unstructured text.

### Global pipeline binding

- `GlobalPipeline`: `places_global_pipeline`
- Bound schema: `Places to Visit` (latest schema fetched at run start)
- Input: unstructured text query (for example, `"stone arch bridge in minneapolis"`)

### Application Stage Design

#### Stage 1: `research` (default sequential stage)

Purpose: compute canonical request context before property fan-out.

Pipelines:
1. `load_latest_schema` pipeline
   - step: fetch newest schema for bound database
2. `query_to_google_cache` pipeline
   - step 1: use Claude to transform raw query into a stronger Google Places request
   - step 2: execute Google Places search and store result in cache/context

This stage is where the previous "gather research" behavior now lives.

#### Stage 2: `property_resolution` (parallel stage)

Purpose: fan out property work using schema computed in Stage 1.

- Build one pipeline per target property.
- Each property pipeline is step-based and can be custom or default.
- Stage uses parallel mode so property pipelines run concurrently, then joins.

#### Stage 3: `image_resolution` (default sequential stage)

Purpose: resolve the image/cover payload after property computation.

- Single pipeline for image retrieval and normalization.
- Optimization and overlap can be added later without changing abstractions.

### Application Diagram (places-entry section)

```
Unstructured input text
        │
        ▼
┌─────────────────────────────────────────┐
│ GlobalPipeline: places_global_pipeline  │
│ schema_binding: "Places to Visit"       │
└───────────────────┬─────────────────────┘
                    │
                    ▼
      ┌─────────────────────────────────┐
      │ Stage 1: research (sequential) │
      ├─────────────────────────────────┤
      │ Pipeline: load_latest_schema    │
      │   Step: fetch_schema            │
      │                                 │
      │ Pipeline: query_to_google_cache │
      │   Step: rewrite_query_claude    │
      │   Step: google_places_to_cache  │
      └───────────────────┬─────────────┘
                          │
                          ▼
      ┌─────────────────────────────────┐
      │ Stage 2: property_resolution    │
      │ run_mode = parallel             │
      ├─────────────────────────────────┤
      │ fan-out: one pipeline/property  │
      │  - custom pipeline if defined   │
      │  - fallback default pipeline    │
      └───────────────────┬─────────────┘
                          │
                          ▼
      ┌─────────────────────────────────┐
      │ Stage 3: image_resolution       │
      │ Pipeline: resolve_cover_image   │
      └───────────────────┬─────────────┘
                          │
                          ▼
                 Assemble page payload
                          │
                          ▼
                 Notion page insert
```

### Property pipeline fallback (unchanged core idea)

```
Schema property "Rating"
        │
        ▼
Custom pipeline registered?
        │
   YES ─┴──► use custom property pipeline
        │
   NO   ▼
Is type in SKIP_TYPES?
        │
   YES ─┴──► skip
        │
   NO   ▼
use default pipeline (AI infer + format)
```

---

## 4. Putting It All Together — Module Layout

```
app/
├── main.py
├── dependencies.py
├── models/
│   └── schema.py                       # DatabaseSchema, PropertySchema, SelectOption
├── services/
│   ├── notion_service.py               # NotionService (delegates to SchemaCache)
│   ├── schema_cache.py                 # SchemaCache with TTL
│   ├── claude_service.py
│   ├── google_places_service.py
│   ├── scraper_service.py              # (future) Website scraping
│   └── places_service.py              # PlacesService (place creation pipeline wrapper)
├── pipeline_lib/
│   ├── core.py                         # GlobalPipeline, Stage, Pipeline, PipelineStep
│   ├── context.py                      # PipelineRunContext / shared state helpers
│   ├── orchestration.py                # Stage runner + fan-out/join logic
│   ├── logging.py                      # Structured logging helpers/bindings
│   ├── default.py                      # DefaultPipeline, InferValueWithAI, FormatForNotionType
│   ├── stage_pipelines/
│   │   ├── schema.py                   # reusable schema-related pipelines
│   │   └── google_places.py            # reusable place-intake pipelines
│   └── steps/
│       ├── google_places.py            # Reusable property steps: ExtractDisplayName, ...
│       └── notion_format.py            # Reusable property steps: FormatAsNotionTitle, ...
├── app_global_pipelines/
│   ├── __init__.py                     # Registry of GlobalPipeline implementations
│   └── places_to_visit.py              # PlacesGlobalPipeline
├── custom_pipelines/
│   ├── __init__.py                     # Convenience imports
│   ├── title.py                        # TitlePipeline
│   ├── primary_type.py                 # PrimaryTypePipeline
│   ├── description.py                  # DescriptionPipeline
│   ├── phone_number.py                 # PhoneNumberPipeline
│   └── website_url.py                  # WebsiteUrlPipeline
└── routes/
    ├── locations.py
    └── test.py
```

### Implementation packaging requirement

When this design is implemented, treat the pipeline abstraction as an internal framework package with publishable quality (as if it could be shipped to pip), and keep application code as a consumer of that package.

Minimum expectations:

- Put abstraction components (`GlobalPipeline`, `Stage`, `Pipeline`, `PipelineStep`, orchestration, context contracts, default/fallback pipeline mechanics) in a dedicated package namespace separate from app-specific business logic.
- Document every public abstraction in code with high-quality docstrings and usage notes (inputs, outputs, lifecycle, concurrency guarantees, failure semantics).
- Add a markdown reference document for the package (for example, `docs/technical-architecture/pipeline-framework.md`) that explains architecture, extension points, execution lifecycle, and authoring examples.
- Keep app code thin: record-specific pipelines, services, and routes should compose the package primitives rather than re-implementing orchestration behavior.

Key structural decisions:

- **`pipeline_lib/`** contains the framework: all base classes, orchestration logic, run-context helpers, logging contracts, default/fallback behavior, and reusable building blocks.
- **`pipeline_lib/stage_pipelines/`** holds reusable stage-level pipelines (schema sync, query transformation, external lookups, cache writes) that app-level stages compose.
- **`pipeline_lib/steps/`** holds reusable `PipelineStep` implementations for property pipelines. These read from shared context and transform data into Notion property formats.
- **`app_global_pipelines/`** contains top-level `GlobalPipeline` subclasses — one per Notion database type. Each defines stage order, stage run mode, and how app behavior composes framework primitives.
- **`custom_pipelines/`** contains the per-property pipeline subclasses. Each file is self-contained and reads from `ResearchContext`.

---

## 5. Design Principles & Tradeoffs

### Why this approach

| Principle | How it's met |
|---|---|
| **Shared abstraction keeps mental model consistent** | Page-level and property-level flows both follow the same structure: global pipeline → stages → pipelines → pipeline steps. This reduces special cases and makes orchestration explicit. |
| **Framework-quality package boundary** | Core pipeline abstractions should be implemented and documented like a reusable package (code docs + markdown guide), and application modules should consume those abstractions instead of duplicating orchestration logic. |
| **Stage boundaries express true dependencies** | Stages are sequential by default. A stage is parallel only when explicitly marked that way, which keeps dependency ordering obvious while still allowing safe fan-out. |
| **Run context is a clean contract boundary** | Stage pipelines and property pipelines communicate through a shared context object. There is one place to inspect gathered data for debugging and AI prompts. |
| **Custom pipelines are explicit and self-contained** | Each custom pipeline is a single file with a single class. The developer declares the property name and the step sequence. Nothing is inferred or magical. |
| **GlobalPipeline reads like a dependency recipe** | Looking at `PlacesGlobalPipeline`, you can immediately see what must happen first, what can overlap, and what must complete before page creation. |
| **Default fallback means the app works for any schema** | If you add a new property in Notion, the app immediately handles it via the AI fallback — with access to *all* gathered data. If the AI guess isn't good enough, you write a custom pipeline. |
| **Sequential-by-default stages reduce orchestration risk** | Stage execution is sequential unless explicitly marked parallel. Parallelism is opt-in and visible in stage definitions, making race conditions easier to reason about. |
| **Fault-tolerant at both levels** | A failing page-level pipeline is logged but doesn't crash unrelated pipelines. A failing property pipeline is logged and its property is skipped. The record still gets inserted with whatever succeeded. |

### Tradeoffs to be aware of

| Tradeoff | Mitigation |
|---|---|
| **First request after TTL expiry is slower** (cache miss) | The TTL can be tuned. Could also add a `/admin/refresh-schema` endpoint for manual cache warming after known Notion changes. |
| **Default pipeline makes a Claude call per unhandled property** | For a schema with many properties and few custom pipelines, this could mean several concurrent Claude calls. Batch the AI calls into one prompt, or increase the custom pipeline coverage for important properties. |
| **Sync services (Claude, Google) need `asyncio.to_thread`** | Wrapping sync calls is straightforward. Alternatively, migrate to async HTTP clients (`httpx.AsyncClient`, async Anthropic client). |
| **Run-context keys are convention-enforced, not type-enforced** | Keys are strings — a typo in `context.get("goggle_place")` silently returns `None`. Mitigation: define key constants in a shared module (e.g., `KEYS.GOOGLE_PLACE = "google_place"`). |
| **Page-level failures may cascade** | If `SearchGooglePlaces` fails, downstream stage pipelines that depend on `"google_place"` will find nothing. Critical dependencies should fail fast so later stages can be skipped safely. |
| **One GlobalPipeline per database type** | This is by design — each database has different data needs. If databases share logic, extract reusable pipelines/steps and compose them into each global pipeline. |

---

## 6. Future Extensions

These are natural extensions that the architecture supports without structural changes:

- **Cover image pipeline with non-blocking overlap** — Start `FetchCoverImage` as soon as `"google_place"` exists. Let it run concurrently with property fan-out, but enforce a final stage barrier so page creation waits for both property payload and cover image result.
- **AI fuzzy matching step** — A reusable `PipelineStep` that uses Claude to pick the best Notion select option when there's no exact match. Any custom pipeline can import and use it.
- **New data sources** — Adding Yelp, Wikipedia, or Foursquare is just a new page-level pipeline in a new or existing stage. Property pipelines that want the data read it from the context; pipelines that don't want it ignore it.
- **Smarter default pipeline** — The default could batch all unhandled properties into a single Claude call instead of one per property, reducing latency and cost. The `ResearchContext.snapshot()` method already provides the data in a format ready for a batch prompt.
- **New record types** — Supporting a new Notion database (e.g., "Restaurants", "Hotels") is a new `GlobalPipeline` subclass with its own stages and custom pipelines. The framework code doesn't change.
- **Conditional stages** — A `GlobalPipeline` could inspect the user query or schema before deciding which stages to run. For example, skip a scraping stage if no property in the schema needs contact info.
- **Auto-discovery** — If the manual import in `custom_pipelines/__init__.py` becomes tedious, the registry could auto-scan the package for `PropertyPipeline` subclasses using `importlib` and `inspect`.
