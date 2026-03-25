# Public beta waitlist page and submission security

**Status:** **Complete on 2026-03-24** — migration `beta_waitlist_submissions`, `POST /public/waitlist`, `notion_pipeliner_ui` `/waitlist` + landing CTA; see `work-log.md` Log.  
**Goal:** Beta user launch - add a public, mobile-safe waitlist flow that captures interest from the landing page without confusing waitlist join with actual invite-based beta access.

---

## 1. Summary

The marketing landing page should stop routing the bottom CTA directly into `/auth` for users who do **not** already have an invitation code. Instead, it should send them to a dedicated public page at **`/waitlist`** with a short form and explicit messaging:

- joining the page means **joining a waitlist**, not creating an account,
- actual beta access still requires a **manual invitation code**,
- the beta is intentionally small and **Notion-only** for now,
- strong-fit submissions will receive a follow-up email and, if selected, an invitation code.

The public form should POST to a new unauthenticated FastAPI route, which will:

1. validate and normalize input,
2. verify a CAPTCHA token server-side,
3. apply API-side abuse checks,
4. insert or update a waitlist record in Supabase using the server-side service role,
5. return a generic success response that does not reveal whether the email was already submitted.

This should be implemented as a **new public intake surface**, not as an extension of invite signup:

- current invite signup is for users who already have a code (`POST /auth/signup`),
- waitlist submission is for users who want to be considered for a future code,
- the public waitlist should not reuse `invitation_codes` rows as a write target.

---

## 2. Why this belongs in technical architecture

This is primarily an engineering design problem, not just landing-page copy. The work spans:

- public frontend routing and responsive form behavior,
- unauthenticated API design,
- Supabase schema and admin data model,
- anti-spam and abuse controls,
- later handoff into the invitation-code system.

For that reason this doc lives under `docs/technical-architecture/productization-technical/beta-launch-readiness/`.

---

## 3. Current codebase context

### 3.1 Landing CTA today

The current bottom CTA lives in `notion_pipeliner_ui/src/routes/landing/BetaCtaSection.tsx`.

- Signed-out users go to **`/auth`**
- Signed-in users go to **`/dashboard`**
- copy assumes the user already has a **20-character invitation code**

That is correct for invite-based signup, but it is the wrong funnel for cold landing-page traffic.

### 3.2 Existing public API patterns

The codebase already has public endpoints that do **not** require managed auth:

- `GET /auth/eula/current` in `app/routes/eula.py`
- `POST /auth/signup` in `app/routes/signup.py`

These show the right route shape for a public endpoint:

- Pydantic request model
- no `Depends(require_*_managed_auth)`
- request-scoped service lookup from `request.app.state`
- consistent JSON error responses via `HTTPException`

### 3.3 Existing frontend public fetch patterns

`notion_pipeliner_ui/src/lib/api.ts` already has unauthenticated fetch helpers such as:

- `getCurrentEula()`
- `signUpWithInvitation(...)`

The new waitlist POST should follow the same `VITE_BASE_URL` and error-shape conventions.

### 3.4 Existing invitation system

The invite system already supports:

- `invitation_codes`
- `POST /auth/invitations` for admin issuance
- `POST /auth/signup` for invite-based account creation
- admin UI for invitations, users, and cohorts

That system should remain the **downstream access-control mechanism**. The waitlist should feed operators toward invitation issuance later, but it should not replace invitation codes.

---

## 4. Product intent and user-facing messaging

### 4.1 CTA wording

Recommended primary CTA label at the bottom of the landing page:

- **Join the beta waitlist**

Acceptable shorter fallback:

- **Join the beta**

Preferred because it is more honest and reduces confusion:

- **Join the beta waitlist**

### 4.2 Waitlist page positioning

The waitlist page should clearly say:

- we are excited about the interest,
- the beta is intentionally small,
- we are focused on **Notion users first** during beta,
- submissions are reviewed manually,
- a waitlist submission does **not** create an account or grant access.

### 4.3 Recommended top-of-page copy

Recommended draft:

> We are excited that you want to try Oleo. Right now the beta is intentionally small so we can stay focused on one thing: building the best possible Notion-first experience before we expand to more destinations. I read these submissions personally. If it looks like a strong fit for the current beta, we will reach out by email with an invitation code.

Short supporting note near the form or submit button:

> Joining the waitlist does not create an account. Beta access still requires an invitation code.

---

## 5. UX architecture

### 5.1 Use a dedicated page, not a modal

Even though the CTA "brings up a form," the implementation should be a dedicated route:

- **Frontend route:** `"/waitlist"`
- **Page component:** `WaitlistPage.tsx` (or `BetaWaitlistPage.tsx`)

Rationale:

- better on mobile than a tall modal,
- simpler keyboard, focus, and screen-reader behavior,
- easier to deep-link and share,
- better for analytics,
- better for future A/B copy changes,
- avoids stacking a long form over an already animated landing page.

### 5.2 Page layout

Desktop:

- centered single-column form card
- generous top copy above the form
- max content width around 40-48rem
- primary button full-width on narrow cards

Mobile:

- full-width stacked layout
- no side-by-side fields
- `min-height: 48px` inputs and button
- textareas large enough to avoid cramped typing
- no decorative motion that competes with form completion

### 5.3 Success state

After submit:

- replace the form with an in-page success confirmation
- keep the user on the same route
- show a short confirmation message and optional return link to `/`
- include a secondary link: "Already have an invitation code? Sign in or sign up"

Do **not** redirect to `/auth` after waitlist submit; that would blur the difference between waiting and actual access.

---

## 6. Form fields

### 6.1 Public fields (v1)

| Field | Type | Required | Notes |
|------|------|----------|------|
| `email` | email input | Yes | Primary outreach channel; normalize to lowercase + trimmed |
| `name` | text input | Yes | Friendly personal follow-up |
| `heardAbout` | select + optional detail text | Yes | Better reporting than free-text only |
| `workRole` | text input | Yes | "What do you do for work?" |
| `notionUseCase` | textarea | Yes | "What workflows do you want to automate with Notion?" |
| `betaFit` | checkbox | Yes | Acknowledge this is a waitlist and beta is Notion-first |

### 6.2 `heardAbout` options

Suggested enum values:

- `friend_or_colleague`
- `x_or_twitter`
- `linkedin`
- `search`
- `notion_community`
- `youtube_or_podcast`
- `other`

If `other`, show a short follow-up text input.

### 6.3 Copy for the acknowledgment checkbox

Recommended:

> I understand this is a waitlist for a small Notion-focused beta, and access still requires an invitation code.

### 6.4 Hidden anti-bot field

Add a hidden honeypot input such as `companyWebsite` or `faxNumber`.

- real users never fill it,
- bots often do,
- if present, the API should accept the request shape but silently treat it as spam.

---

## 7. Frontend implementation plan

### 7.1 Route and composition

Add a new public route in `notion_pipeliner_ui/src/main.tsx`:

- `"/waitlist"` under the existing public layout

Add a new page component:

- `src/routes/WaitlistPage.tsx`

Add a small API helper in `src/lib/api.ts`:

- `submitBetaWaitlist(...)`

### 7.2 Landing CTA changes

Update `src/routes/landing/BetaCtaSection.tsx`:

- change primary CTA target from `/auth` to `/waitlist` for signed-out users
- keep signed-in users going to `/dashboard`
- update note copy so it no longer assumes the user already has an invite

Recommended new bottom-section copy:

- title: **Join the beta waitlist**
- sub-copy: **We are keeping beta small and focused on Notion users first. Tell us what you want to automate and we will reach out if you are a fit.**
- note: **Waitlist join does not create an account. Invitation code required for access.**

### 7.3 Responsive behavior

Requirements:

- single-column form at all breakpoints
- label-above-input layout
- no sidecar imagery required for v1
- support Safari mobile, Chrome mobile, and desktop
- allow browser autofill for name and email

### 7.4 Accessibility

- semantic `form`, `label`, `fieldset`, and `legend` where useful
- inline validation with `aria-describedby`
- submit button disabled only while request is in flight, not pre-emptively hidden
- clear success and failure messaging announced to assistive tech

---

## 8. Backend API design

### 8.1 New route

Create a new public router and mount it from `app/main.py`.

Recommended endpoint:

- `POST /public/waitlist`

Why not `/auth/...`:

- this is not authentication,
- it keeps public marketing intake separate from account creation,
- it avoids future confusion with invite signup and EULA flows.

### 8.2 Request model

Example JSON body:

```json
{
  "email": "person@example.com",
  "name": "Jane Smith",
  "heardAbout": "linkedin",
  "heardAboutOther": null,
  "workRole": "Operations lead at a B2B SaaS company",
  "notionUseCase": "I want to turn meeting notes and lead notes into structured database entries in Notion.",
  "betaFitAccepted": true,
  "captchaToken": "token-from-turnstile",
  "companyWebsite": ""
}
```

### 8.3 Response behavior

Success should be intentionally generic:

- **HTTP 202 Accepted**
- body like `{ "status": "accepted" }`

Return the same generic success for:

- new submission
- duplicate submission for the same email
- spammy honeypot-hit payloads that you choose to drop silently

This prevents the endpoint from becoming an email enumeration tool.

### 8.4 Validation failures

Use explicit validation for:

- malformed email
- missing required fields
- overlong text
- `heardAboutOther` required when `heardAbout == "other"`
- `betaFitAccepted` must be `true`
- invalid or missing CAPTCHA token

Recommended status codes:

- **400** bad or incomplete user input
- **429** rate limited
- **500** unexpected internal failure

---

## 9. Persistence design

### 9.1 New table

Create a dedicated table:

- `beta_waitlist_submissions`

This should be separate from:

- `invitation_codes`
- `user_profiles`
- `user_cohorts`

Because this data is pre-auth, marketing-adjacent, and may contain many people who never become users.

### 9.2 Proposed schema

| Column | Type | Notes |
|------|------|------|
| `id` | UUID PK | generated |
| `email` | text | original user-entered email |
| `email_normalized` | text | lowercase trimmed version; unique |
| `name` | text | required |
| `heard_about` | text | enum-like string |
| `heard_about_other` | text nullable | required only for `other` |
| `work_role` | text | required |
| `notion_use_case` | text | required |
| `status` | text | default `PENDING_REVIEW` |
| `submission_source` | text | default `landing_page_waitlist` |
| `submission_count` | integer | default `1`; increments on duplicate email resubmits |
| `first_submitted_at` | timestamptz | immutable |
| `last_submitted_at` | timestamptz | updated on duplicate |
| `captcha_provider` | text | e.g. `turnstile` |
| `captcha_verified_at` | timestamptz nullable | audit trail |
| `client_ip_hash` | text nullable | salted hash, never raw IP |
| `user_agent` | text nullable | trimmed length |
| `referrer` | text nullable | if present |
| `invitation_code_id` | UUID nullable | FK to `invitation_codes(id)` once invited |
| `invited_at` | timestamptz nullable | when operator issues invite |
| `reviewed_at` | timestamptz nullable | optional future admin workflow |
| `admin_notes` | text nullable | optional future admin workflow |
| `created_at` | timestamptz | default now |
| `updated_at` | timestamptz | default now |

### 9.3 Duplicate handling

Use `email_normalized` as the dedupe key.

If the same email submits again:

- keep the row,
- update the latest answers,
- increment `submission_count`,
- update `last_submitted_at`,
- keep returning the same generic success response.

This gives operators better history without multiplying rows for the same person.

### 9.4 RLS

Enable RLS on the table, but do **not** add anonymous insert policies for the browser.

Why:

- the browser should not write directly to Supabase,
- the existing app already uses the Render-hosted FastAPI server as the public API boundary,
- keeping writes server-side avoids exposing table access patterns to anonymous clients.

In practice:

- **service role** or trusted backend client writes the row,
- admin-only reads can be added later through FastAPI,
- no public `select`, `insert`, `update`, or `delete` policy is needed for the website.

---

## 10. Security and abuse prevention

### 10.1 Threat model

This route is public and unauthenticated, so the main concerns are:

- automated spam,
- scripted DB-filling attacks,
- repeated requests from the same IP,
- email enumeration,
- oversized payloads,
- malicious strings intended for logs or admin UIs.

### 10.2 Recommended layered defenses

Use **all** of the following:

1. **Server-side CAPTCHA verification**
2. **API-side rate limiting**
3. **Honeypot field**
4. **Strict length and shape validation**
5. **Generic success response for duplicates**
6. **No direct browser write to Supabase**
7. **RLS enabled on the table**

### 10.3 CAPTCHA recommendation

Use **Cloudflare Turnstile** on the frontend and verify it in FastAPI.

**Operational setup:** See [Cloudflare Turnstile setup guide](./cloudflare-turnstile-setup-guide.md) (dashboard widget, hostnames, keys, env vars).

Why this is the preferred fit:

- good UX on mobile and desktop,
- works for arbitrary custom forms,
- keeps bot filtering close to the public page,
- does not require exposing any privileged Supabase capability.

### 10.4 What Supabase helps with, and what it does not

Supabase helps with:

- storing the waitlist table,
- RLS on the table,
- admin-side data access later,
- optional future DB-backed rate-limit tables or review tooling.

Supabase does **not** directly solve the custom FastAPI route problem by itself.

Important distinction from current docs:

- Supabase CAPTCHA documentation is primarily for **Supabase Auth** forms such as sign-up/sign-in.
- Our proposed waitlist route is a **custom FastAPI endpoint**, not a native Supabase Auth flow.
- Supabase `db_pre_request` hooks apply to the **Supabase Data API (PostgREST)**, not to requests that first land on our Render-hosted FastAPI app.

So for this feature:

- **Vite** is only the frontend build/runtime shell,
- **Render** hosts the public API,
- **FastAPI** must do request validation, CAPTCHA verification, and rate limiting,
- **Supabase** should remain the protected persistence layer behind that API.

### 10.5 Rate limiting recommendation

Do not rely on in-memory rate limiting only, because it becomes unreliable if the API scales horizontally.

Recommended v1 approach:

- add a small DB-backed rate-limit store keyed by a salted hash of client IP + route + time bucket,
- enforce a modest threshold such as "N submissions per IP per hour",
- return **429** when exceeded,
- keep raw IPs out of storage.

If implementation simplicity wins for v1, an app-layer limiter can ship first, but it should be treated as a temporary guardrail rather than the final architecture.

### 10.6 Logging and data hygiene

- do not log full request bodies at INFO level
- trim long strings before logging
- hash IP before storage
- escape or sanitize text before displaying it in future admin UIs
- do not render waitlist answers as raw HTML anywhere

---

## 11. Backend implementation structure

### 11.1 New service and repository

Do **not** overload `SupabaseAuthRepository` with this feature.

Recommended additions:

- `app/services/beta_waitlist_service.py`
- `app/repositories/` or `app/services/` companion repository such as `supabase_beta_waitlist_repository.py`
- `app/routes/public_waitlist.py`

Rationale:

- waitlist intake is not auth,
- keeps concerns separated,
- avoids turning the auth repository into a catch-all marketing/storefront data layer.

### 11.2 App state wiring

In `app/main.py`:

- instantiate the repository and service during startup,
- attach them to `app.state`,
- `include_router(public_waitlist.router)`.

### 11.3 API flow

1. receive request body
2. reject obvious bad payloads
3. short-circuit honeypot hits
4. verify CAPTCHA token with provider
5. check rate limit
6. normalize and upsert waitlist submission
7. return `202 accepted`

---

## 12. Admin and downstream invitation flow

### 12.1 Immediate v1 scope

For the first implementation, it is acceptable if the public feature only supports:

- public submission
- durable storage

and does **not yet** include a full admin review UI.

### 12.2 Intended next step

The natural follow-up is an admin waitlist list/detail workflow, likely under a future route such as:

- `/admin/waitlist`

or as a new tab near the existing admin users/invitations tools.

### 12.3 Bridge into invitation issuance

When an operator wants to invite someone from the waitlist:

- issue an invitation code using the existing admin invitation flow,
- default `issuedTo` to the waitlist email,
- default `platformIssuedOn` to `beta-waitlist`,
- store `invitation_code_id` and `invited_at` back on the waitlist row.

That gives a clean bridge from public interest -> operator review -> invite code -> `/auth` signup.

---

## 13. Testing plan

### 13.1 Frontend

- CTA routes signed-out users from landing page to `/waitlist`
- `/waitlist` renders correctly on mobile-width and desktop-width tests
- form validation blocks missing required fields
- success state replaces form after accepted response
- duplicate accepted response still shows same success state

### 13.2 Backend

- valid request returns `202`
- invalid email / missing fields returns `400`
- `heardAbout == other` requires detail text
- honeypot-filled request does not create a real row
- duplicate email updates existing row instead of inserting a second row
- CAPTCHA verification failure returns `400`
- rate-limited client returns `429`

### 13.3 Manual

- iPhone-size browser
- Android-size browser
- desktop Safari/Chrome
- slow network submit behavior
- keyboard-only and screen-reader smoke test

---

## 14. Recommended implementation sequence

1. Add schema migration for `beta_waitlist_submissions`
2. Add backend repository, service, and `POST /public/waitlist`
3. Add CAPTCHA verification support and env vars
4. Add `submitBetaWaitlist(...)` client helper
5. Add `/waitlist` page
6. Repoint the landing CTA from `/auth` to `/waitlist`
7. Add tests
8. Add admin review tooling in a later pass

---

## 15. Key decisions

| Question | Decision |
|------|------|
| Modal or page? | **Dedicated page** at `/waitlist` |
| Reuse `/auth`? | **No** - keep waitlist separate from account creation |
| Direct browser write to Supabase? | **No** - go through FastAPI |
| Use existing `invitation_codes` table? | **No** - add `beta_waitlist_submissions` |
| How to communicate access? | Explicitly: **waitlist first, invitation code later** |
| Beta scope messaging? | Explicitly: **Notion-first during beta** |
| Core anti-abuse stack? | CAPTCHA + rate limit + honeypot + validation + RLS |

---

## Related documents

- [Oleo marketing homepage - scrollytelling](./oleo-homepage-scrollytelling-architecture.md) - current landing-page section architecture; Section 08 currently defers form wiring
- [Marketing landing page - mobile-friendly](./landing-page-mobile-friendly-architecture.md) - responsive CTA and mobile interaction guidance
- [Admin users, invitations & cohorts UI](./admin-invitation-management-ui.md) - downstream invitation issuance system and `platformIssuedOn` conventions
- [EULA versioning, acceptance, and admin management](./eula-versioning-and-acceptance.md) - example of current public-route plus admin-route structure
- [p2_pr06 - Sign Up with Invite Code and User Type Assignment](../phase-2-authentication-segmentation/p2_pr06-sign-up-with-invite-code-and-user-type-assignment.md) - existing invite-based signup flow that should remain distinct from waitlist intake

---

## Revision history

| Version | Date | Notes |
|------|------|------|
| 1 | 2026-03-24 | Initial architecture for public landing-page waitlist capture, public API intake, Supabase persistence, and anti-abuse design. |
