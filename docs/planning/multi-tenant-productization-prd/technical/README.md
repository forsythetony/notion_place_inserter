# Technical Documentation

Phase-specific technical documents for the multi-tenant productization project. For significant decisions and rationale, see the [Decision Log](../decision-log.md). Architecture notes, API specs, migration guides, and implementation details live in the phase subfolders below.

For phase scope and context, see the [Recommended Phasing](../initial-planning/multi-tenant-productization-prd.md#recommended-phasing) section of the PRD.

## Phase folders

| Phase | Folder | PRD summary |
|-------|--------|-------------|
| 1 | [phase-1-platform-migration](./phase-1-platform-migration/) | Migrate off Render; establish hosting baseline; minimal frontend + API |
| 2 | [phase-2-authentication-segmentation](./phase-2-authentication-segmentation/) | Add auth; user-based segmentation; minimal UI |
| 3 | [phase-3-yaml-backed-product-model](./phase-3-yaml-backed-product-model/) | Define data model; load from local YAML |
| 4 | [phase-4-datastore-backed-definitions](./phase-4-datastore-backed-definitions/) | Move config to datastore; text-based editing |
| 5 | [phase-5-visual-editing](./phase-5-visual-editing/) | Visual pipeline editor; dual view (visual + structured) |
