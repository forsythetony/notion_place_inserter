# PR 08 - Deployment Runbook and Render Exit

## Objective

Finalize Phase 1 by documenting and validating the new deployment baseline, and de-emphasizing Render as the primary production path.

## Scope

- Update `README.md` deployment guidance to Supabase-centered architecture.
- Add environment matrix for:
  - API process
  - worker process
  - frontend process
- Add migration/cutover runbook:
  - pre-cutover checklist
  - cutover steps
  - rollback plan
- Update or retire Render-first instructions/config where appropriate.

## Expected changes

- Documentation updates across `README.md` and planning docs.
- Any required deployment config templates/scripts for new flow.
- Clear smoke-test checklist for post-deploy validation.

## Acceptance criteria

- New team member can deploy using docs without relying on Render-first assumptions.
- Cutover and rollback steps are explicit and executable.
- Phase 1 docs, plan, and runbook are internally consistent.

## Out of scope

- Phase 2 auth rollout or tenant policy implementation.

## Dependencies

- Requires PR 07.
