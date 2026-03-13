# Supabase Local User Creation Errors - Findings and Suggestions

Date: 2026-03-13
Scope: Local Supabase user creation failures showing:
`Failed to create user: API error happened while trying to communicate with the server.`

## Findings

1. Local Supabase stack is up and reachable.
   - `supabase status` reports Studio, Auth API, DB, and related services as running.
   - Studio page itself is reachable on both:
     - `http://127.0.0.1:54323`
     - `http://localhost:54323`

2. The failing endpoint is the admin user creation path, not general Auth.
   - Auth logs show requests to `POST /admin/users` failing with:
     - `403`
     - `error_code: bad_jwt`
     - `msg: invalid JWT ... signing method HS256 is invalid`
   - This indicates token validation mismatch on admin calls.

3. Regular signup works locally.
   - `POST /auth/v1/signup` succeeds with `200` and returns tokens.
   - This isolates the problem to admin-create flow (`/admin/users`) rather than basic Auth service availability.

4. Current config has host inconsistencies that can increase local auth friction.
   - `supabase/config.toml` sets Studio `api_url` to `http://localhost:54321` (good note in file).
   - Project URLs in status and Makefile dashboard helper currently use `127.0.0.1`.
   - Mixed `localhost`/`127.0.0.1` usage is a known source of local auth/cookie/CSP confusion.

## Most likely root cause

The local stack is rejecting the token presented to `/auth/v1/admin/users` due to JWT algorithm/issuer expectations mismatch (`HS256` token rejected during admin verification).

This is consistent with:
- explicit `bad_jwt` errors in auth logs for `/admin/users`
- successful non-admin signup flow
- generic Studio/UI message masking the underlying auth error

## Suggestions (ordered)

1. Short-term unblock: use signup flow for local testing of user creation.
   - Use `sign up` (`/auth/v1/signup`) for creating test accounts while admin-create is being fixed.

2. Standardize local host usage to `localhost` everywhere.
   - Open Studio via `http://localhost:54323` (not `127.0.0.1`).
   - Update helper commands/docs to use `localhost` consistently.
   - Align `site_url` and redirect URLs in `supabase/config.toml` with local frontend URL host choice.

3. Refresh local auth runtime to clear key/config drift.
   - `supabase stop`
   - `supabase start`
   - if needed: `supabase db reset` (only if local data can be reset)

4. Verify Supabase CLI version and upgrade if stale.
   - Newer local stacks have had auth key handling changes.
   - After upgrade, restart the stack and retest admin user creation in Studio.

5. Diagnose with auth logs while reproducing.
   - Run `docker logs -f supabase_auth_notion_place_inserter`
   - Reproduce "Add user" in Studio
   - Confirm whether `bad_jwt` persists or changes to a different actionable error.

## Resolution update (applied)

The issue was resolved locally by:

1. Standardizing host config:
   - `make supabase-dashboard` now opens `http://localhost:54323`
   - `auth.site_url` updated to `http://localhost:3000`
   - redirect allow-list expanded to include localhost and 127.0.0.1 variants
2. Upgrading Supabase CLI:
   - from `v2.75.0` to `v2.78.1`
3. Restarting local stack:
   - `supabase stop && supabase start`

After these changes, `POST /auth/v1/admin/users` returned `200` in direct local verification and auth logs showed successful `user_signedup` audit events for admin-created users.

## Suggested verification checklist

- [ ] Studio opened via `http://localhost:54323`
- [ ] Frontend local URL and Supabase `site_url` use same host style
- [ ] Admin user create in Studio succeeds
- [ ] No `bad_jwt` for `/admin/users` in auth logs
- [ ] `/auth/v1/signup` still succeeds

## Notes

- No evidence from current migrations indicates schema constraints are blocking `auth.users` inserts.
- The failure signature points to auth token verification for admin endpoints, not DB schema shape.
