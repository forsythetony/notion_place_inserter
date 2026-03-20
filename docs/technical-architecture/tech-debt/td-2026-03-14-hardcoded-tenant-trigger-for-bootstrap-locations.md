# Tech Debt Story: Hardcoded Tenant Trigger for Bootstrap Locations

## ID

- `td-2026-03-14-hardcoded-tenant-trigger-for-bootstrap-locations`

## Status

- Backlog

## Why this exists

A tenant-specific trigger was added at `product_model/tenants/871ba2fa-fd5d-4a81-9f0d-0d98b348ccde/triggers/trigger_http_locations.yaml` to give a specific user access to the bootstrap locations job. This is an ad-hoc workaround; the bootstrap fallback already allows any user to resolve the locations trigger when they have no tenant-specific trigger. The hardcoded tenant file duplicates the bootstrap trigger and couples the product model to a specific user UUID.

## Goal

Remove the hardcoded tenant trigger and rely on the existing bootstrap fallback, or implement a proper mechanism for granting users access to bootstrap jobs (e.g. tenant provisioning, explicit allowlist in config, or per-user bootstrap opt-in).

## In Scope

- Delete `product_model/tenants/871ba2fa-fd5d-4a81-9f0d-0d98b348ccde/triggers/trigger_http_locations.yaml`.
- Remove the empty tenant directory if no other tenant-specific config exists.
- Confirm the bootstrap fallback in `YamlTriggerRepository.get_by_path` already serves all users (tenant triggers first, then bootstrap).
- Document the intended behavior: bootstrap triggers are shared starters; tenant triggers override when present.

## Out of Scope

- Changing the bootstrap fallback logic.
- Per-user bootstrap opt-in or allowlist (separate story if needed).

## Suggested Validation Tasks

1. Verify `POST /triggers/{user_id}/locations` resolves for any `user_id` via bootstrap fallback when no tenant trigger exists.
2. Remove the hardcoded tenant trigger file.
3. Run `make test-locations` and `tests/test_locations_route.py` to confirm no regressions.
4. If the specific user needs guaranteed access, document the alternative (e.g. they use `/triggers/bootstrap/locations` or rely on fallback).

## Acceptance Criteria

- No tenant-specific YAML files hardcode user UUIDs for bootstrap job access.
- Bootstrap locations trigger remains available to all users via fallback.
- Tests pass.

## Primary Code Areas

- `product_model/tenants/871ba2fa-fd5d-4a81-9f0d-0d98b348ccde/triggers/` (delete)
- `app/repositories/yaml_repositories.py` (YamlTriggerRepository.get_by_path fallback behavior)

## Notes

- The bootstrap fallback in `get_by_path` checks tenant triggers first, then bootstrap. Any user calling `/triggers/{their_user_id}/locations` should already resolve to the bootstrap trigger when they have no tenant override. The hardcoded file was added before confirming this behavior or for an explicit “this user gets it” guarantee; clearing it simplifies the model.
