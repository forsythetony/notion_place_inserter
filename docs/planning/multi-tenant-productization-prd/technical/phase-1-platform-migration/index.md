# Phase 1 PR Task Index

This folder breaks the Phase 1 Supabase migration into PR-sized tasks. Complete them in order to reduce merge conflicts and avoid coupling frontend/deployment work to unfinished backend foundations.

## Required order

1. [`pr-01-supabase-bootstrap-and-migrations.md`](./pr-01-supabase-bootstrap-and-migrations.md)
2. [`pr-02-phase1-schema-and-queue-foundation.md`](./pr-02-phase1-schema-and-queue-foundation.md)
3. [`pr-03-backend-supabase-config-and-client-layer.md`](./pr-03-backend-supabase-config-and-client-layer.md)
4. [`pr-04-locations-enqueue-path-migration.md`](./pr-04-locations-enqueue-path-migration.md)
5. [`pr-05-worker-consumer-and-run-lifecycle-persistence.md`](./pr-05-worker-consumer-and-run-lifecycle-persistence.md)
6. [`pr-06-minimal-frontend-trigger-ui.md`](./pr-06-minimal-frontend-trigger-ui.md)
7. [`pr-07-tests-observability-and-api-doc-updates.md`](./pr-07-tests-observability-and-api-doc-updates.md)
8. [`pr-08-deployment-runbook-and-render-exit.md`](./pr-08-deployment-runbook-and-render-exit.md)

## Why this sequence

- PRs 1-2 establish Supabase project and durable data/queue primitives.
- PRs 3-5 migrate runtime behavior (`/locations` and worker) without changing product UX.
- PR 6 adds the minimal UI only after backend API behavior is stable.
- PRs 7-8 harden tests/docs and finalize deployment runbook for Render runtime + Supabase platform.

## Completion definition for this phase

Phase 1 is complete when PRs 1-8 are merged and validated together in a shared environment:

- `/locations` uses durable queueing (not in-memory) in production flow
- run lifecycle is persisted in Supabase
- minimal frontend (Render Static Site) can trigger a run
- docs/deploy path document Render runtime (API/worker/UI) + Supabase platform integration
