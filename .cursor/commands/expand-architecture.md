# Expand architecture document

**Invocation:** Run this command, then **attach the target doc** with `@` (e.g. `@docs/technical-architecture/productization-technical/beta-launch-readiness/global-and-per-user-resource-limits.md`). If no file is attached, ask for a path before proceeding.

## Goal

Expand the **attached markdown file in place**: deeper design, gaps, interfaces, risks, and links—grounded in this repo, sibling docs, and (when needed) authoritative external sources.

## Workflow

### 1. Anchor on the target doc

- Read the full attached file. Note its title, intent, audience, and any explicit TODOs or stubs.
- Identify what “expanded” means here: missing sections (e.g. data model, API surface, failure modes, rollout, observability), thin bullets that need detail, or outdated statements.

### 2. Mine internal context (do this before writing)

- **Related docs:** Same directory and parents under `docs/`; cross-links already in the file; `docs/technical-architecture/work-log.md` (especially the **Architecture document index** and **Goal** tables). Follow links to phase specs, runbooks, and tech-debt notes that touch the same subsystem.
- **Codebase:** Search and read implementations that correspond to claims in the doc (`app/`, `supabase/`, and if present in the workspace, `notion_pipeliner_ui/src/`). Prefer primary sources (handlers, migrations, routes) over guesses.
- **Placement:** Follow `docs-placement` rules in `.cursor/rules/docs-placement.mdc`—expand content **in the file the user attached**; do not spawn separate docs unless the user asked or the placement rules clearly require a split.

### 3. Online research (when it helps)

Use the web when internal sources are insufficient, for example:

- External APIs, protocols, SLAs, or security expectations.
- Vendor or product behavior (e.g. Notion, Supabase, queue semantics).
- Industry patterns or naming that should align with common usage.

Prefer primary documentation and recent sources. Summarize conclusions in the doc; do not paste long quotes.

### 4. What to add (typical expansions)

Use judgment—only sections that strengthen the doc:

- **Context & boundaries** — In/out of scope; dependencies on other services or docs.
- **Design** — Flows, sequences, state, contracts (schemas, message shapes, idempotency).
- **Operational** — Deployment, migrations, feature flags, rollback, rate limits, quotas.
- **Observability & failure** — Metrics, logs, alerts, degraded behavior, user-visible errors.
- **Security & privacy** — AuthZ, PII, secrets, tenant isolation if relevant.
- **Open questions / phased follow-ups** — Explicit gaps; link to `docs/technical-architecture/tech-debt/` when appropriate.

Use Mermaid only when a diagram clarifies control flow or architecture (keep diagrams small and maintainable).

### 5. Edit discipline

- **Edit the attached file** with concrete additions and fixes; preserve the doc’s voice and structure unless reorganization clearly helps.
- Fix internal links and headings; avoid duplicating large slabs of other docs—**link** to them and summarize.
- After substantive changes, if the doc lives under `docs/technical-architecture/` and the index in `work-log.md` tracks it, update the **Architecture document index** per `.cursor/rules/architecture-doc-index.mdc` (e.g. **Unexpanded** → **Ready for review** when appropriate).

### 6. Finish

- Give a short summary of what was expanded and which areas remain intentionally thin.
- **Services to restart:** None (documentation-only). If you changed application code while researching, say so per `service-restart-check.mdc`.
