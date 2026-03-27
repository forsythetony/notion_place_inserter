# Beta launch readiness — architecture hub

High-level architecture and delivery tracking for **beta** and **expanded beta** work. Individual topics live in linked documents.

## Launch stages

Phasing uses **launch stage** terminology (see **Goals → Launch stages** in [`docs/technical-architecture/work-log.md`](../../work-log.md)):

| Launch stage | What it is | Engineering posture |
|--------------|------------|---------------------|
| **Launch stage 1** | The **beta** phase — validate the **product idea** with direct feedback | **At most ten** concurrent beta users. **Not** a gate for horizontal worker scaling or a full observability/telemetry program; prioritize learning whether the idea works. |
| **Launch stage 2** | **Expanded beta** — grow beyond the initial cohort | **Scalability** (e.g. worker horizontal scaling, queue/DB coordination) and **observability** (error handling, metrics, traces, operator telemetry) are explicit priorities before further expansion. |

**Goal 1** in the work log maps to **Launch stage 1** only. Open pushes for **Launch stage 2** are listed separately there so they are not treated as blockers for the first beta.

## Goal

See **Goals → Goal 1: Beta user launch (Launch stage 1)** in [`docs/technical-architecture/work-log.md`](../../work-log.md) for authoritative open/complete tables and status.

## Open architecture pushes (inventory)

_Status and stage alignment: prefer the work-log tables; this inventory may lag on minor edits._

### Launch stage 1 (beta, ≤10 users)

Core scope first; **polish tracks are scheduled toward the end of the stage** (see Goal 1 table in [`work-log.md`](../../work-log.md)).

| Document | Status |
|----------|--------|
| [First pipeline — time to value](./first-pipeline-time-to-value-architecture.md) (signup → first run; optional step-through) | **Open** · **Ready for review** |
| [Tech Deck: Admin Providers page](./tech-deck-admin-providers-page.md) (usage providers & rate cards UI) | **Open** · **Ready for review** |
| [Admin Users directory — user detail modal](./admin-users-directory-user-detail-modal.md) | **Not started** · **Ready for review** |
| [Oleo marketing homepage — scrollytelling](./oleo-homepage-scrollytelling-architecture.md) | **In progress** — **remaining:** add live demo to `/` · **Ready for review** |
| [Beta example demo video — recording and hosting plan](./beta-example-demo-video-recording-and-hosting-plan.md) | **In progress** · **Ready for review** |
| [Cross-page UI — general polish](./beta-ui-general-polish.md) | **Open** — **later** in Launch stage 1 · **Ready for review** |
| [Pipeline cell / step detail UI polish](./pipeline-cell-step-detail-ui-polish.md) | **Open** — **latest** in Launch stage 1 (after cross-page polish) · **Ready for review** |

### Launch stage 2 (expanded beta — scaling & observability)

| Document | Status |
|----------|--------|
| [Worker horizontal scaling and queue coordination](./worker-horizontal-scaling-and-queue-coordination.md) | **Open** · **Ready for review** |
| [Error handling, observability, and telemetry](./error-handling-observability-and-telemetry.md) | **Open** · **Ready for review** |

### Shipped or complete (either stage / shared prerequisites)

| Document | Status |
|----------|--------|
| [Admin invitation management UI](./admin-invitation-management-ui.md) (invites + **user cohorts**) | **Complete on 2026-03-22** · **Ready for review** |
| [Public product name and positioning](./public-product-name-and-positioning.md) | **Complete on 2026-03-24** (Oleo chosen) · **Ready for review** |
| [Global and per-user resource limits](./global-and-per-user-resource-limits.md) | **Complete on 2026-03-22** · **Ready for review** |
| [Enhanced user monitoring and cost tracking](./enhanced-user-monitoring-and-cost-tracking.md) | **Complete on 2026-03-24** · **Ready for review** (cost rollups follow-up: [td-2026-03-24-monitoring-cost-rollups-aggregation.md](../../tech-debt/td-2026-03-24-monitoring-cost-rollups-aggregation.md)) |
| [Landing page — live demo video (“See it in action”)](./landing-page-live-demo-see-it-in-action-architecture.md) | **Complete on 2026-03-24** · **Ready for review** |
| [Marketing landing page — mobile-friendly](./landing-page-mobile-friendly-architecture.md) | **Complete on 2026-03-23** · **Ready for review** |
| [Public beta waitlist page and submission security](./public-beta-waitlist-submission-architecture.md) | **Complete on 2026-03-24** · **Ready for review** |
| [Admin waitlist directory, beta waves, and invite-from-waitlist](./admin-waitlist-waves-and-invitations-architecture.md) | **Complete on 2026-03-26** · **Ready for review** |
| [Admin Users — Waves tab](./admin-users-waves-tab-architecture.md) (`beta_waves` CRUD UI; tab before Cohorts) | **Complete on 2026-03-26** · **Ready for review** |
| [Data targets — source management modal](./data-targets-source-management-modal.md) | **Complete on 2026-03-25** · **Ready for review** |
| [Invitations tab readability & accessibility](./invitations-tab-readability-and-accessibility.md) | **Complete on 2026-03-22** · **Ready for review** |
| [Invitations — create invitation modal](./invitations-create-invitation-modal.md) | **Complete on 2026-03-22** · **Ready for review** |
| [Users & cohorts tabs — UI parity with Invitations](./admin-users-and-cohorts-ui-parity-with-invitations.md) | **Complete on 2026-03-22** · **Ready for review** |
| [EULA versioning, acceptance, and admin management](./eula-versioning-and-acceptance.md) | **Complete on 2026-03-23** · **Ready for review** |

_Status values for review readiness: **Unexpanded** = brief only, no detailed design. **Ready for review** = architecture/spec written. **Reviewed** = human sign-off (none recorded yet). Combine with delivery state where relevant. See Goal 1 in [`work-log.md`](../../work-log.md)._

When a doc ships or is superseded, update the [Architecture document index](../../work-log.md) and this file.
