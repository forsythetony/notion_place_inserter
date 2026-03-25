# Beta launch readiness — architecture hub

High-level architecture and delivery tracking for work required before a **small-group beta** launch. Individual topics live in linked documents; most are **placeholders** until expanded.

## Goal

See **Goals → Goal 1: Beta user launch** in [`docs/technical-architecture/work-log.md`](../../work-log.md).

## Open architecture pushes (inventory)

| Document | Status |
|----------|--------|
| [Admin invitation management UI](./admin-invitation-management-ui.md) (invites + **user cohorts**) | **Complete on 2026-03-22** · **Ready for review** |
| [Public product name and positioning](./public-product-name-and-positioning.md) | **Complete on 2026-03-24** (Oleo chosen) · **Ready for review** |
| [Global and per-user resource limits](./global-and-per-user-resource-limits.md) | **Open** · **Ready for review** |
| [Enhanced user monitoring and cost tracking](./enhanced-user-monitoring-and-cost-tracking.md) | **Complete on 2026-03-24** · **Ready for review** (cost rollups/aggregation follow-up: [td-2026-03-24-monitoring-cost-rollups-aggregation.md](../../tech-debt/td-2026-03-24-monitoring-cost-rollups-aggregation.md)) |
| [Worker horizontal scaling and queue coordination](./worker-horizontal-scaling-and-queue-coordination.md) | **Open** · **Ready for review** |
| [Error handling, observability, and telemetry](./error-handling-observability-and-telemetry.md) | **Open** · **Ready for review** |
| [Oleo marketing homepage — scrollytelling](./oleo-homepage-scrollytelling-architecture.md) | **In progress (MVP 2026-03-23)** · **Ready for review** |
| [Landing page — live demo video (“See it in action”)](./landing-page-live-demo-see-it-in-action-architecture.md) | **Complete on 2026-03-24** · **Ready for review** |
| [Beta example demo video — recording and hosting plan](./beta-example-demo-video-recording-and-hosting-plan.md) | **In progress** · **Ready for review** |
| [Marketing landing page — mobile-friendly](./landing-page-mobile-friendly-architecture.md) | **Not started** · **Unexpanded** |
| [Public beta waitlist page and submission security](./public-beta-waitlist-submission-architecture.md) | **Complete on 2026-03-24** · **Ready for review** |
| [Admin waitlist directory, beta waves, and invite-from-waitlist](./admin-waitlist-waves-and-invitations-architecture.md) | **Not started** · **Ready for review** |
| [Beta UI general polish](./beta-ui-general-polish.md) | **Open** · **Ready for review** |
| [Data targets — source management modal](./data-targets-source-management-modal.md) | **Complete on 2026-03-25** · **Ready for review** |
| [Invitations tab readability & accessibility](./invitations-tab-readability-and-accessibility.md) | **Complete on 2026-03-22** · **Ready for review** |
| [Invitations — create invitation modal](./invitations-create-invitation-modal.md) | **Complete on 2026-03-22** · **Ready for review** |
| [Users & cohorts tabs — UI parity with Invitations](./admin-users-and-cohorts-ui-parity-with-invitations.md) | **Complete on 2026-03-22** · **Ready for review** |
| [Pipeline cell / step detail UI polish](./pipeline-cell-step-detail-ui-polish.md) | **Open** — **schedule toward end of beta prep** · **Ready for review** |
| [Tech Deck: Admin Providers page](./tech-deck-admin-providers-page.md) (usage providers & rate cards UI) | **Open** · **Ready for review** |
| [EULA versioning, acceptance, and admin management](./eula-versioning-and-acceptance.md) (`eula_versions`, signup modal, `/admin/eula`) | **Complete on 2026-03-23** · **Ready for review** |

_Status values for review readiness: **Unexpanded** = brief only, no detailed design. **Ready for review** = architecture/spec written. **Reviewed** = human sign-off (none recorded yet). Combine with delivery state where relevant. See Goal 1 in [`work-log.md`](../../work-log.md)._

When a doc ships or is superseded, update the [Architecture document index](../../work-log.md) and this table.
