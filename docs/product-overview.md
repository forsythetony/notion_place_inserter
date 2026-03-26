# Oleo — Product Overview

**Living document.** This is the canonical reference for what Oleo is, who it serves, how it works, and how it's built. Update it as the product evolves.

**Last updated:** 2026-03-25

---

## Mission

Oleo exists to turn messy, unstructured inputs into clean, structured Notion records — automatically, reliably, and without maintaining custom scripts.

You paste (or send) raw data. Oleo parses, enriches, classifies, and routes it through a configurable pipeline. Notion gets the rest.

The product is built for people who treat Notion as an operational system of record and are tired of brittle automations, schema mismatches, and manual cleanup.

---

## What Oleo does (in one paragraph)

Oleo is a hosted pipeline product that lets authenticated users create **triggers** (HTTP webhooks, iOS Shortcuts, cron jobs), connect them to **visual pipelines** (stages of enrichment, AI classification, validation), and write structured outputs into **Notion databases** — with schema awareness, guardrails, and full run history. The first fully productized flow is the **Place Inserter**: share a restaurant name from your phone, and Oleo researches it, enriches it with Google Places data and AI-generated cover images, and writes a complete record to your Notion database.

---

## Sample flow: Places pipeline

A concrete example of how Oleo works end-to-end today:

1. **Trigger** — You're at a restaurant. You select the name in Safari, tap Share → "Send to Oleo" (an iOS Shortcut that fires an authenticated HTTP POST).
2. **Intake** — Oleo receives the raw text (e.g. *"Rintaro, San Francisco"*) via the HTTP trigger and enqueues a job.
3. **Research stage** — The pipeline's first stage calls **Google Places API** to resolve the name into structured place data (address, coordinates, cuisine, rating, hours).
4. **Enrichment stage** — A parallel step calls **Freepik** to generate or find a cover image that matches the place.
5. **AI classification** — **Claude** (Anthropic) reads the enriched data and assigns tags, categories, and constrained property values based on the user's configured taxonomy.
6. **Property Set (terminal step)** — The pipeline enforces that every property-configuring path ends with a `Property Set` step — a guardrail ensuring only valid, schema-aligned data reaches Notion.
7. **Write to Notion** — Oleo writes the structured record (name, location, cuisine, tags, rating, cover image, coordinates) to the user's chosen Notion database.
8. **Notification** — A WhatsApp message (or other configured channel) confirms: *"Rintaro added to your Places database."*
9. **Audit** — The full run is visible in Activity History: trigger payload, per-stage status, per-step outputs, errors, and estimated API cost.

This same pipeline architecture generalizes to CRM leads, content operations, research ingestion, product ideas — any flow where unstructured input needs to become a structured Notion record.

---

## Who we're building for

### Primary audience

Technically comfortable operators, founders, and power users in small teams (1–20 people) who use Notion as a system of record and need **reliable, automated ingestion** into Notion databases.

### Firmographic profile

- **Company type:** Startups, agencies, creator businesses, small product teams
- **Tooling maturity:** Already using forms, webhooks, or automation tools (Zapier, Make, n8n)
- **Notion usage:** Multiple active databases tied to real operations (CRM, content, inventory, research)

### Behavioral signals (strong fit)

- Existing fragile automations that break on schema changes
- Frequent manual cleanup of AI-generated or externally ingested records
- Need to explain or audit what changed and why
- Repeated property-mismatch errors when writing to Notion from external sources

### Anti-ICP for V1

- Teams seeking broad cross-app automation first (we are Notion-first)
- Enterprise buyers needing SSO, advanced RBAC, and procurement compliance from day one
- Users who don't treat Notion as an operational system

### Positioning statement

For Notion power users running operational workflows, Oleo is a Notion-first pipeline product that turns incoming data into clean, structured Notion updates with guardrails, reusable components, and run visibility — without maintaining brittle scripts.

---

## Core product concepts

| Concept | What it means |
|---------|---------------|
| **Trigger** | The event that starts a pipeline run — an authenticated HTTP endpoint, an iOS Shortcut action, a webhook, or a cron schedule. Users create and manage triggers in the UI. |
| **Job** | A configured workflow definition that connects a trigger to a pipeline and a data target. Jobs have stages; stages contain pipelines. |
| **Stage** | A logical grouping within a job (e.g. "research," "enrichment," "classification"). Stages contain one or more pipelines. |
| **Pipeline** | An ordered sequence of pipeline steps within a stage. Pipelines call external APIs, run AI, validate data, and transform outputs. |
| **Pipeline Step** | A single operation in a pipeline — an API call, an AI prompt, a validation check, a property assignment. Steps are reusable components. |
| **Property Set** | A terminal pipeline step that enforces schema alignment before writing to the target. Any pipeline that configures a property must end with this step. |
| **Data Target** | A Notion database (V1) that the pipeline writes to. Users select the database, expose specific fields, and sync the schema. |
| **Data Source** | An external API or provider that a pipeline step calls for enrichment (Google Places, Freepik, etc.). |
| **Run** | A single execution of a job, traceable end-to-end from trigger payload to written output. |

---

## Tech stack

### Backend (Python)

| Layer | Technology |
|-------|------------|
| API framework | **FastAPI** (async, type-safe) |
| Runtime | **Uvicorn** (ASGI server) |
| Database | **Supabase Postgres** (managed; RLS for tenant isolation) |
| Queue | **pgmq** (Postgres-native message queue via Supabase) |
| Auth | **Supabase Auth** (JWT sessions, invite-code gating, user types) |
| AI | **Anthropic Claude** (classification, constrained output, property value selection) |
| Places enrichment | **Google Places API** |
| Image generation | **Freepik API** |
| Notifications | **Twilio** (WhatsApp) |
| Notion writes | **notion-client** (official Notion SDK) |
| HTTP client | **httpx** (async) |
| Logging | **Loguru** |
| Config | **python-dotenv**, **PyYAML** |

### Frontend (TypeScript)

| Layer | Technology |
|-------|------------|
| Framework | **React 19** + **Vite** |
| Routing | **React Router v7** |
| Pipeline editor | **React Flow** (`@xyflow/react`) |
| Auth client | **Supabase JS** (`@supabase/supabase-js`) |
| Animation (marketing) | **GSAP** + **MotionPathPlugin** |
| Icons | **Lucide React** |
| Search | **Fuse.js** (client-side fuzzy search) |
| Bot protection | **Cloudflare Turnstile** (`@marsidev/react-turnstile`) |
| Typography | **Geist** font family |
| Testing | **Vitest** + **React Testing Library** |

### Infrastructure

| Concern | Provider |
|---------|----------|
| API + Worker hosting | **Render** (Web Service) |
| Frontend hosting | **Render** (Static Site) |
| Database + Auth + Queue | **Supabase** (Postgres, Auth, pgmq) |
| Bot protection | **Cloudflare Turnstile** |
| DNS / Domains | **Namecheap** (migration to Oleo branding in progress) |

### Data model (key entities)

User, Workspace, Integration Connection, Connector Credentials, Data Target, Target Schema, Trigger, Trigger–Job Link, Job Definition, Stage Definition, Pipeline Step Template, Pipeline Run, Step Run, Activity Event, Invitation Code, User Profile, EULA Version, Beta Waitlist Submission, UI Theme Preset, App Config, Resource Limits.

---

## Design language

### Philosophy: Calm Graphite

The visual system is dark-first, neutral, and restrained. The goal is a modern, calm product that supports high information density without feeling cramped — inspired by Linear's hierarchy and clarity, but with more breathing room and softer contrast transitions.

### Core principles

1. **Clarity over decoration** — Every visual element supports comprehension or action.
2. **Consistent surfaces** — Public pages and authenticated app share the same tokens, typography, and spacing.
3. **Explicit feedback** — Clear hover, focus, active, and disabled states everywhere.
4. **Accessibility by default** — WCAG-oriented contrast minima, visible focus indicators, 36px minimum touch targets.

### Token palette

| Token | Hex | Role |
|-------|-----|------|
| Background | `#111318` | Base canvas |
| Surface-1 | `#161A22` | Sidebar, cards, panels |
| Surface-2 | `#1C212B` | Dropdowns, modals |
| Border | `#2A3140` | Low-contrast dividers |
| Primary text | `#E8EDF5` | Headings, body |
| Secondary text | `#A9B3C3` | Captions, placeholders |
| Accent | `#7AA2F7` | Actions, links, selected elements |
| Success | `#59C08B` | Positive states |
| Warning | `#D9A35B` | Caution states |
| Danger | `#D66A6A` | Errors, destructive actions |

### Marketing / landing page visual language

The public-facing marketing homepage uses a distinct but compatible visual layer on top of the core system: dark desaturated background (`~#12111A`), warm white type (`~#E8E4DF`), indigo–violet accent (`~#6366F1`). Motion is slow and meditative (GSAP, no bounce/elastic, duration floor ~0.8s). Depth is conveyed through blur gradients, not hard edges.

### App shell layout

- **Left sidebar:** Pipelines, Triggers, Database Targets, Account (Surface-1 background; accent highlight on active item)
- **Top utility bar:** Search, account controls, quick-create (48px minimum height)
- **Content area:** Background token base; 24px padding, 32px for editor
- **Base spacing scale:** 8px (steps: 8, 12, 16, 24, 32)

### Typography

- **Font:** Geist (display + body)
- **Minimum body size:** 14–15px
- **Contrast:** ≥ 4.5:1 for body/small text; ≥ 3:1 for large text and UI controls

Full style guide: [`notion_pipeliner_ui/styleguide/`](../notion_pipeliner_ui/styleguide/README.md)

---

## Product architecture (phases)

Oleo was built through a phased productization from a single-user CLI prototype to a multi-tenant hosted product:

| Phase | What shipped |
|-------|-------------|
| **Phase 1** | Platform migration — Supabase Postgres + pgmq queue; Render API/worker; minimal frontend with one-button trigger |
| **Phase 2** | Authentication — Supabase Auth, invite-code gating, user types (Admin / Standard / Beta Tester), basic sign-in/sign-up |
| **Phase 3** | YAML-backed product model — triggers, targets, pipelines, stages, and steps loaded from local YAML definitions |
| **Phase 4** | Datastore-backed definitions — pipeline config persisted in Postgres; text-based editing in the UI |
| **Phase 5** | Visual editing — React Flow pipeline editor; full CRUD for triggers, targets, stages, steps through the UI |
| **Beta prep** | Homepage, EULA, waitlist, admin tools (invitations, cohorts, monitoring, cost tracking, resource limits), domain/brand migration |

---

## Integrations

| Integration | Role | Status |
|-------------|------|--------|
| **Notion** | Primary write destination — database target, schema sync, page creation | Production |
| **Google Places** | Location enrichment — address, coordinates, cuisine, rating, hours | Production |
| **Freepik** | AI image generation for covers and visual enrichment | Production |
| **Claude (Anthropic)** | AI classification, constrained output, tag assignment, property value selection | Production |
| **iOS Shortcuts** | Mobile trigger — share sheet → HTTP POST to Oleo | Production |
| **WhatsApp (Twilio)** | Completion notifications | Production |
| **Webhooks** | Generic HTTP trigger for any external caller | Production |
| **Google Sheets** | Future target/source | Planned |
| **Slack** | Future notification channel | Planned |

---

## Current status

**Stage:** Private beta preparation (Goal 1: beta user launch).

**What works today:**
- Authenticated multi-user access with invite-code gating
- Full pipeline CRUD through visual editor (React Flow)
- HTTP triggers with provisioned endpoints and auth
- Notion OAuth connection and schema-aware database targeting
- Async job execution with Supabase pgmq queue
- Google Places, Freepik, and Claude enrichment
- Per-run observability and activity history
- Admin tools: user management, invitations, cohorts, monitoring, cost tracking, resource limits, EULA management
- Marketing homepage with GSAP scrollytelling animation
- Public beta waitlist with Cloudflare Turnstile

**In progress / upcoming:**
- Pipeline zoom/viewport behavior polish
- Worker horizontal scaling architecture
- Error handling and observability (OTEL evaluation)
- Cross-page UI polish pass
- Domain migration (Notion Pipeliner → Oleo branding across all surfaces)
- Beta example demo video
- Admin waitlist directory and invite-from-waitlist flow

---

## Related documents

| What | Where |
|------|-------|
| Product name and positioning | [`docs/technical-architecture/productization-technical/beta-launch-readiness/public-product-name-and-positioning.md`](./technical-architecture/productization-technical/beta-launch-readiness/public-product-name-and-positioning.md) |
| Multi-tenant productization PRD | [`docs/feature-proposals/multi-tenant-productization-prd.md`](./feature-proposals/multi-tenant-productization-prd.md) |
| Go-to-market brief | [`docs/marketing/go-to-market-brief-notion-powerusers-2026-03-12.md`](./marketing/go-to-market-brief-notion-powerusers-2026-03-12.md) |
| Homepage scrollytelling architecture | [`docs/technical-architecture/productization-technical/beta-launch-readiness/oleo-homepage-scrollytelling-architecture.md`](./technical-architecture/productization-technical/beta-launch-readiness/oleo-homepage-scrollytelling-architecture.md) |
| Design direction (Calm Graphite) | [`docs/style/design-direction-options.md`](./style/design-direction-options.md) |
| UI style guide | [`notion_pipeliner_ui/styleguide/README.md`](../notion_pipeliner_ui/styleguide/README.md) |
| Work log and decision history | [`docs/technical-architecture/work-log.md`](./technical-architecture/work-log.md) |
| Beta launch readiness hub | [`docs/technical-architecture/productization-technical/beta-launch-readiness/README.md`](./technical-architecture/productization-technical/beta-launch-readiness/README.md) |
