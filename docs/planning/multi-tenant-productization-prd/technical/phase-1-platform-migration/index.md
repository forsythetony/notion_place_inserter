# Phase 1 PR Task Index

This folder breaks the Phase 1 Supabase migration into PR-sized tasks. Complete them in order to reduce merge conflicts and avoid coupling frontend/deployment work to unfinished backend foundations.

## Required order

1. [`p1_pr01-supabase-bootstrap-and-migrations.md`](./p1_pr01-supabase-bootstrap-and-migrations.md)
2. [`p1_pr02-schema-and-queue-foundation.md`](./p1_pr02-schema-and-queue-foundation.md)
3. [`p1_pr03-backend-supabase-config-and-client-layer.md`](./p1_pr03-backend-supabase-config-and-client-layer.md)
4. [`p1_pr04-locations-enqueue-path-migration.md`](./p1_pr04-locations-enqueue-path-migration.md)
5. [`p1_pr05-worker-consumer-and-run-lifecycle-persistence.md`](./p1_pr05-worker-consumer-and-run-lifecycle-persistence.md)
6. [`p1_pr06-minimal-frontend-trigger-ui.md`](./p1_pr06-minimal-frontend-trigger-ui.md)
7. [`p1_pr07-tests-observability-and-api-doc-updates.md`](./p1_pr07-tests-observability-and-api-doc-updates.md)
8. [`p1_pr08-deployment-runbook-and-render-exit.md`](./p1_pr08-deployment-runbook-and-render-exit.md)

## Why this sequence

- p1_pr01–p1_pr02 establish Supabase project and durable data/queue primitives.
- p1_pr03–p1_pr05 migrate runtime behavior (`/locations` and worker) without changing product UX.
- p1_pr06 adds the minimal UI only after backend API behavior is stable.
- p1_pr07–p1_pr08 harden tests/docs and finalize deployment runbook for Render runtime + Supabase platform.

## Completion definition for this phase

Phase 1 is complete when p1_pr01–p1_pr08 are merged and validated together in a shared environment:

- `/locations` uses durable queueing (not in-memory) in production flow
- run lifecycle is persisted in Supabase
- minimal frontend (Render Static Site) can trigger a run
- docs/deploy path document Render runtime (API/worker/UI) + Supabase platform integration
