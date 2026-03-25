# Frontend session cache for account context (admin flag + runtime theme)

**Status:** **Complete on 2026-03-23**  
**Date:** 2026-03-23  
**Area:** `notion_pipeliner_ui` — authenticated shell, first paint

## Problem

On full page refresh (and sometimes on first navigation into the app shell), the UI **flashes**: layout or chrome briefly shows the non-admin experience and/or default styling, then updates after network calls complete.

Users perceive this as jarring even when data loads quickly.

## Prior behavior (before cache)

1. **`AppShell`** (`src/layouts/AppShell.tsx`) initialized `isAdmin` to `false`. After `accessToken` was available it called `getManagementAccount` → `GET /management/account` and set `isAdmin` from `user_type === "ADMIN"`. Until the response returned, the sidebar rendered **without** the Admin group even for admin users.

2. **`useRuntimeUiTheme`** (`src/hooks/useRuntimeUiTheme.ts`) initialized `cssVars` to `undefined`, then loaded `GET /theme/runtime` and applied variables on `.app-shell`. Until then, the shell had **no** runtime theme variables from the API.

Both effects were keyed only on `accessToken`, so **every reload** repeated the “empty → filled” transition. In-memory React state did not survive a browser refresh.

## Goal

- Treat **account role for UI chrome** (`user_type` / admin sidebar) as **hint data** that can be shown immediately from a **durable client cache** tied to the signed-in user, with a background refresh to correct drift.
- Optionally apply the same pattern to **runtime theme** (`cssVars` from `/theme/runtime`) so colors and tokens do not pop in after first paint.
- **Security posture:** Admin actions remain enforced by the API; the cache only affects which nav links and styling appear before the network confirms. Stale UI that briefly shows or hides admin chrome is acceptable given server-side gates (per product stance).

## Implementation (2026-03-23)

- **`sessionStorage`**, keys `pipeliner:account-context:<user_id>` and `pipeliner:ui-theme-runtime:<user_id>` — see [`notion_pipeliner_ui/src/lib/accountChromeCache.ts`](../../../notion_pipeliner_ui/src/lib/accountChromeCache.ts) (sibling repo / workspace folder).
- **`AppShell`:** reads cached `user_type` synchronously for initial `isAdmin`; revalidates with `getManagementAccount`, writes cache on success; **does not** force `isAdmin` to `false` on fetch error (keeps cached hint).
- **`useRuntimeUiTheme(accessToken, userId)`:** hydrates `cssVars` from cache on first paint; revalidates with `fetchUiThemeRuntime`; on error, keeps prior/cached `cssVars` when possible.
- **`AuthProvider.signOut`:** calls `clearSessionCachesForUser(user.id)` for the signed-in user.

Stale-while-revalidate flow matches the recommended approach below.

## Recommended approach

### 1. Persisted cache keyed by Supabase user id

- Read `user.id` from `authState` when `status === "authenticated"`.
- Store a small JSON blob, e.g. `{ userType: string, fetchedAt: number }`, under a key such as `pipeliner:account-context:<user_id>` in **`sessionStorage`** or **`localStorage`**.
  - **`sessionStorage`:** Survives reload and navigation in the same tab; cleared when the tab closes. Good default for “session locally” without long-lived cross-session bleed.
  - **`localStorage`:** Survives new tabs and browser restarts; slightly more risk of stale chrome if an admin is demoted and only opens a new tab days later—still correctable on the next `GET /management/account`.
- On shell mount, **synchronously** read the cache for the current `user.id` and use it to initialize `isAdmin` (or a small `AccountChromeContext`) **before** the first paint of nav that depends on it, then **revalidate** with `getManagementAccount` and update state + cache when the response arrives.

This is **stale-while-revalidate**: first paint matches last known server truth; network may adjust once.

### 2. Invalidation and consistency

| Event | Action |
|--------|--------|
| **Sign out** | Remove cached entries for that user (or clear the whole key namespace used by the app). |
| **User id changes** (different login) | Cache miss; do not reuse another user’s blob. |
| **Successful `getManagementAccount`** | Replace cache with latest `user_type` (and optionally other cheap fields if needed later). |
| **Failed fetch** | Keep showing cached hint if present; avoid flipping admin chrome to `false` only because of transient errors (optional policy). |

### 3. Runtime theme (`/theme/runtime`)

The same flash affects **theme variables** applied on `.app-shell`. Options:

- **A (minimal):** Cache the last `UiThemeRuntimeResponse` (or just `cssVars` + `presetId` + `schemaVersion`) under `pipeliner:ui-theme-runtime:<user_id>` with the same revalidation flow as account context.
- **B (lighter):** Inject a `<style>` tag early from cache in `AppShell` or a small provider mounted under auth, still refreshing in the background.

If admins change the active preset frequently, background refresh after paint is enough; users may see an old theme for one paint—usually acceptable compared to a hard flash to un-themed chrome.

### 4. Optional: `sessionStorage` mirror for OAuth redirect flows

If any path does a full redirect that loses in-memory state but keeps the same session, the persisted cache still helps. Not required for the basic reload case.

### 5. Testing

- Unit tests: cache read/write helpers; key includes `user.id`; sign-out clears or ignores stale keys.
- Component tests: with a primed cache, `AppShell` renders admin nav on first render without waiting for `getManagementAccount` (mock fetch delayed).

## Out of scope / non-goals

- Replacing server-side authorization (unchanged).
- Caching full `ManagementAccountResponse` for limits—other screens can keep fetching as today; this note targets **shell chrome and theme** only unless we later unify.

## Related code

- `notion_pipeliner_ui/src/lib/accountChromeCache.ts` — sessionStorage read/write + `clearSessionCachesForUser`
- `notion_pipeliner_ui/src/layouts/AppShell.tsx` — `isAdmin` + `getManagementAccount`
- `notion_pipeliner_ui/src/hooks/useRuntimeUiTheme.ts` — `fetchUiThemeRuntime`
- `notion_pipeliner_ui/src/auth/AuthProvider.tsx` — sign-out cache clear
- `notion_pipeliner_ui/src/lib/api.ts` — `getManagementAccount`, `fetchUiThemeRuntime`
