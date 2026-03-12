# Decision Log

A chronological record of significant decisions made during the multi-tenant productization project. Use this to capture rationale, alternatives considered, and context for future reference.

## Format

Each entry should include:

- **Date** — When the decision was made
- **Title** — Short name for the decision
- **Context** — What prompted the decision
- **Options considered** — Alternatives that were evaluated
- **Decision** — The chosen direction and why
- **Consequences** — Known trade-offs or follow-up actions

---

## Entries

<!-- Add new entries at the top, most recent first -->

### 2026-03-12 - Select Supabase as Phase 1 platform foundation

- **Date** — 2026-03-12
- **Title** — Supabase-first platform migration (Phase 1)
- **Context** — The PRD required moving off Render and establishing a durable baseline for backend APIs, datastore, async processing, and future auth/tenant isolation. The current codebase relies on shared-secret auth and in-memory queueing, which are not sufficient for productization.
- **Options considered** —
  1. Supabase-centric platform with queue + Postgres foundation
  2. Firebase + Cloud Run + Cloud SQL
  3. Clerk + Neon + Vercel (+ separate jobs platform)
  4. Keep Render-centric architecture for initial productization
- **Decision** — Use a Supabase-first architecture for Phase 1. Implement durable queueing and run persistence in Supabase Postgres (`pgmq` + SQL migrations), keep the existing Python execution engine as a worker for compatibility, and ship a minimal frontend that calls the migrated endpoint. Defer end-user auth UX and tenant policy enforcement to Phase 2.
- **Consequences** —
  - Positive: aligns with PRD direction toward one ecosystem; enables durable async jobs, run history, and a clean path to RLS-based tenant isolation.
  - Trade-off: introduces a hybrid interim architecture (Supabase control plane + Python worker execution plane) instead of an immediate full rewrite to Supabase Edge Functions.
  - Follow-up: create migration-runbook and queue adapter, then replace in-memory queue dependency in `/locations` path.
