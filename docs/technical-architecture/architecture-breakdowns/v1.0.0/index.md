# Architecture Breakdown v1.0.0

This folder contains an implementation-aligned architecture deep dive for the current application.

## Start Here

1. Read `overview.md` for the high-level system model.
2. Continue with `runtime-and-request-flow.md` for startup and API lifecycle behavior.
3. Use `pipeline-architecture.md` to understand orchestration internals.
4. Read `services-and-integrations.md` for service boundaries and external dependencies.
5. Review `data-and-context-contracts.md` for run-context and payload assembly semantics.
6. Finish with `operations-and-observability.md` for logging and operational constraints.

## Document Map

- [Overview](./overview.md)
- [Runtime and Request Flow](./runtime-and-request-flow.md)
- [Pipeline Architecture](./pipeline-architecture.md)
- [Services and Integrations](./services-and-integrations.md)
- [Data and Context Contracts](./data-and-context-contracts.md)
- [Operations and Observability](./operations-and-observability.md)

## Source of Truth

These docs are derived from implementation behavior in `app/` and aligned with:

- `docs/technical-architecture/pipeline-framework.md`
- `docs/technical-architecture/architecture-design.md`
