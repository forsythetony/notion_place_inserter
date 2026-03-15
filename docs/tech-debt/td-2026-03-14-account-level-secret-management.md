# Tech Debt Story: Account-Level Secret Management

## ID

- `td-2026-03-14-account-level-secret-management`

## Status

- Backlog

## Why this exists

Phase 3 trigger endpoints use a shared SECRET for all users. The SECRET is configurable at deployment but not per account. Per-account secret management is required for multi-tenant isolation and secure webhook-style trigger invocation.

## Goal

Replace shared SECRET with per-account (or per-workspace) secret management so each user/tenant can have their own authorization credentials for trigger invocation.

## In Scope

- Design and implement per-account secret storage (e.g. in Supabase, encrypted).
- Update `POST /triggers/{user_id}/{path}` auth to validate against account-specific secret.
- Provide UI or API for users to configure/rotate their trigger secret.
- Migration path from shared SECRET to per-account secrets.

## Out of Scope

- Vault/secret backend integration (Phase 4 may consider).
- Full OAuth or API-key management for third-party integrations.

## Suggested Validation Tasks

1. Define schema for account-level secrets (e.g. `user_trigger_secrets` or similar).
2. Implement secret validation in trigger route.
3. Add configuration endpoint or UI for secret management.
4. Document migration from shared SECRET.

## Acceptance Criteria

- Each account can have a trigger secret (or use shared secret during transition).
- Trigger invocation validates against the account's secret when configured.
- Backward compatibility for shared SECRET during migration period.

## Primary Code Areas

- `app/routes/locations.py` (trigger invocation)
- `app/dependencies.py` (auth validation)
- `notion_pipeliner_ui` (secret configuration UI)

## Notes

- Phase 3 uses shared SECRET for simplicity; this story is the follow-up for production readiness.
