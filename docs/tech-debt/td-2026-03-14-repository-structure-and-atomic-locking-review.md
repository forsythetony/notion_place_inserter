# Tech Debt Story: Repository Structure and Atomic Locking Review

## ID

- `td-2026-03-14-repository-structure-and-atomic-locking-review`

## Status

- Backlog

## Why this exists

Phase 3 introduces repository interfaces and a YAML-backed storage path before Phase 4 database persistence. This increases the need to validate repository boundaries, write patterns, and concurrency behavior so we do not carry structural issues into later phases.

Without a focused review, we risk:
- repository responsibilities drifting and becoming tightly coupled to storage details,
- non-atomic update flows producing partial writes or inconsistent snapshots,
- missing lock/serialization controls causing race conditions in concurrent operations,
- and avoidable rework during the Phase 4 Postgres/Supabase migration.

## Goal

Review and harden repository structure and critical write/read-modify-write paths to ensure atomicity and correct locking/serialization behavior where required.

## In Scope

- Review repository organization and boundaries across domain/service/storage layers.
- Identify operations that must be atomic (especially save/update/delete and run/event persistence flows).
- Verify current locking/serialization strategy for concurrent access paths (worker + API paths).
- Define recommended patterns for atomic operations by backend type:
  - filesystem/YAML (temp file + fsync + atomic rename, per-entity write boundaries),
  - Postgres/Supabase (transactions, row-level locks where needed, idempotency guards).
- Capture concrete follow-up tickets for any high-risk findings.

## Out of Scope

- Full repository rewrite.
- Broad performance optimization not tied to atomicity or locking correctness.
- Infrastructure migration decisions beyond current Phase 3/4 roadmap.

## Suggested Validation Tasks

1. Build a map of repository responsibilities and entity ownership boundaries.
2. Enumerate all read-modify-write operations and classify atomicity requirements.
3. Validate current implementations for partial-write, race, and lost-update risks.
4. Add/expand tests for concurrency-sensitive and idempotency-sensitive paths.
5. Produce implementation guidance/checklist for future repository additions.
6. Split discovered defects into prioritized fix stories.

## Acceptance Criteria

- Repository boundaries and responsibilities are documented and reviewed.
- Atomic operations are explicitly identified with required guarantees.
- Locking/serialization expectations are defined for both YAML and Postgres adapters.
- At least one test plan exists for each high-risk concurrent path.
- Follow-up implementation tasks are documented for all material findings.

## Primary Code Areas to Review

- `app/domain/`
- `app/services/`
- `app/queue/worker.py`
- `app/routes/`
- `tests/`

## Notes

- Prioritize correctness over abstraction purity; this story is intended to prevent data integrity regressions as repository implementations expand in p3_pr03+.
