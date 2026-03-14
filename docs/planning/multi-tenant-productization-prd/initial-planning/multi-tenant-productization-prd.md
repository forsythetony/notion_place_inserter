# PRD: Multi-Tenant Pipeline Productization

## Status

- Draft
- First target productization: Notion Place Inserter

## Summary

The current Notion Place Inserter prototype is valuable and already delivers useful personal functionality. The next step is to evolve it into a multi-user product with authentication, persistent storage, a management UI, and a generalized pipeline system that can support multiple users, reusable pipeline components, and future non-Notion targets.

This product should preserve the core abstractions that already fit the domain well:

- `Stage`
- `Pipeline`
- `PipelineStep`

It should also preserve the opinion that any pipeline which configures a target property must terminate in a `Property Set` pipeline step.

## Problem

The current implementation is optimized for a single operator and a single target workflow. It lacks:

- Multi-user authentication and account boundaries
- Persistent storage for users, configs, executions, and audit history
- A UI for managing data targets, triggers, pipelines, and account setup
- A generalized product model that can grow beyond one hardcoded Notion workflow
- Deployment architecture suitable for both frontend and backend product surfaces

As a result, the current system is useful as a test harness, but it is not yet a durable product platform.

## Product Vision

Build a hosted workflow product that allows authenticated users to create AI-assisted data pipelines that ingest data from triggers, run reusable and configurable pipeline stages, and write structured outputs into user-selected targets.

The first supported target is Notion. The first end-to-end productized use case is the current Notion Place Inserter flow.

## Goals

1. Support multiple users with secure authentication and tenant isolation.
2. Persist product state in a real datastore, likely Postgres.
3. Provide a web UI for setup, configuration, monitoring, and history.
4. Let users create and manage custom pipelines without editing code.
5. Retain the existing execution model of stages, pipelines, and pipeline steps.
6. Introduce reusable pipeline components so common behaviors can be configured, not reimplemented.
7. Support Notion well now without coupling the architecture permanently to Notion.

## Non-Goals

1. Supporting many target systems in V1. Only Notion needs to be production-ready first.
2. Building a full no-code workflow ecosystem comparable to Zapier in V1.
3. Solving enterprise-grade permissions, SSO, or advanced RBAC in the first release.
4. Rewriting every existing pipeline primitive before validating the first productized UI flow.

## Target Users

### Primary User

A technically comfortable operator or founder who wants to configure AI-assisted ingestion pipelines into structured systems like Notion without maintaining custom scripts.

### Secondary User

A team member who needs a shared operational UI to review runs, inspect failures, manage integrations, and modify pipeline behavior safely.

## Core User Stories

1. As a user, I can create an account and securely log in.
2. As a user, I can connect my Notion workspace and authorize access to one or more databases.
3. As a user, I can select a Notion database as a data target and choose which fields should be exposed to a pipeline.
4. As a user, I can create a trigger, including an authenticated HTTP trigger, without manually provisioning backend code.
5. As a user, I can define pipeline stages and pipeline steps in the UI.
6. As a user, I can use reusable pipeline components instead of rebuilding common logic from scratch.
7. As a user, I can inspect execution history and understand what happened in a run.
8. As a user, I can update pipeline configuration without redeploying the application.

## V1 Product Scope

### Authentication and Multi-Tenancy

- User accounts with secure authentication
- Tenant-aware storage and request scoping
- User-based tenancy in V1
- Per-user ownership of:
  - data targets
  - integrations
  - triggers
  - pipelines
  - pipeline runs
  - activity history
- The data model should leave room for a future migration to workspace/team-based tenancy if needed.

### Persistent Storage

Use a relational datastore, most likely Postgres, to persist:

- users
- workspaces or tenants
- auth identities and sessions
- integrations and credentials metadata
- data targets
- exposed target fields
- triggers and trigger auth configuration
- pipeline definitions
- pipeline stage definitions
- pipeline step definitions
- run history
- audit/activity logs

Secrets should not be stored in plaintext in application tables. Use encrypted storage or a secrets-management pattern for provider credentials and trigger secrets.

### Management UI

The product should include a web UI with, at minimum:

- Login and account setup
- Integrations/account connection setup
- Data Targets management
- Triggers management
- Pipeline builder/editor
- Activity history / run history
- Basic operational status and failure visibility

### Target Configuration

The initial left-nav mental model should include:

1. `Data Targets`
2. `Triggers`
3. `Pipelines`
4. `Activity History`
5. `Account Setup`

#### Data Targets

From `Data Targets`, a user can:

- Create a new target
- Select `Notion` as the initial target type
- Choose a Notion database
- Discover its available fields
- Select which fields are exposed for downstream pipeline configuration

This should be modeled generically enough that future target types can expose their own schema or field system through the same product concept.

For V1, schema sync can be rudimentary. Users should be able to manually refresh or sync the target schema when fields change in Notion, rather than relying on advanced automatic schema detection.

#### Triggers

From `Triggers`, a user can:

- Create a new trigger
- Select `HTTP Trigger`
- Automatically provision an authenticated HTTP endpoint
- View the endpoint URL, auth requirements, and expected payload shape
- Associate the trigger with one or more pipelines

The HTTP trigger experience should minimize manual setup and make the contract obvious.

#### Pipelines

From `Pipelines`, a user can:

- Create or edit a pipeline
- Add, remove, and reorder stages
- Add, remove, and configure steps within a pipeline
- Reuse existing step types across multiple pipelines
- Validate that any property-configuring pipeline ends with `Property Set`
- Work visually by default while retaining the ability to switch to a structured text view

## Functional Requirements

### 1. Authentication

- The system must support user sign-up, login, logout, and session management.
- The system must restrict access to tenant-owned resources.
- The system must support secure credential storage for connected integrations.
- V1 should use a managed authentication solution rather than framework-native or fully custom auth.
- A managed auth platform in the category of `Supabase Auth` is the preferred direction because it aligns with the goal of managing the application end to end within one ecosystem.
- Phase 2 onboarding UX must include:
  - a barebones public landing page
  - a `Sign In / Sign Up` entry point in the upper-right header area
  - a dedicated basic auth page for sign-in and sign-up
- After successful authentication, users must be redirected to the dashboard landing page.
- The system must support user types in V1 with exactly these values:
  - `ADMIN`
  - `STANDARD`
  - `BETA_TESTER`
- Sign-up in Phase 2 should be invite-code-gated for non-admin onboarding, with user type assignment determined by the claimed invitation code.

### 1a. Invitation Codes and Access Gating

- The system must introduce an invitation code model stored in the backend and linked to user profile information.
- Each invitation code record must include:
  - `code` (random 20-character string)
  - `date_issued` (datetime)
  - `date_claimed` (datetime, nullable)
  - `issued_to` (free-text field; email or username)
  - `platform_issued_on` (free-text field)
  - `claimed` (boolean)
  - `claimed_at` (datetime, nullable)
  - `user_type` (enum: `ADMIN`, `STANDARD`, `BETA_TESTER`)
- Claim semantics:
  - Invitation codes must be single-use.
  - A claimed code must be marked claimed and timestamped.
  - The newly created user must be assigned the `user_type` on the invitation code.
- The backend must provide a manual operational path to generate invitation codes (script/CLI for operator use).

### 2. Data Target Abstraction

- The system must support a target abstraction separate from Notion-specific implementation details.
- A target must expose a schema/field selection experience in the UI.
- V1 must support Notion database selection and field exposure.
- The target abstraction should be extensible to future targets without redesigning core pipeline concepts.
- V1 schema synchronization for Notion targets can be manual and user-initiated.
- The UI should provide a straightforward way for a user to refresh the target schema and re-expose fields after upstream Notion changes.

### 3. Trigger Abstraction

- The system must support triggers as first-class configurable entities.
- V1 must support an authenticated HTTP trigger.
- Creating an HTTP trigger must provision:
  - a unique endpoint
  - auth guard behavior
  - expected payload contract metadata
- Trigger invocations must be logged and traceable to downstream runs.

### 4. Pipeline Modeling

- The system must preserve `Stage`, `Pipeline`, and `PipelineStep` as core abstractions.
- Users must be able to define pipelines through the UI rather than code-only configuration.
- V1 pipeline editing should be 100% visual.
- The product should support switching between visual and structured-definition views for users who want that flexibility.
- Stages must contain one or more pipelines.
- Pipelines must contain ordered pipeline steps.
- Pipeline definitions must be stored in the datastore.
- V1 does not need pipeline versioning or draft/published workflow states.
- The data model should leave room to add pipeline versioning and publish workflows later without major redesign.
- Pipeline definitions should have a canonical structured representation that can be serialized and deserialized cleanly.
- YAML is a strong candidate for that representation because it is human-readable and makes view-switching easier, though the exact persisted format can remain implementation-dependent as long as YAML import/export or equivalent ser/de is supported.

### 4a. Visual and Structured Definition Views

- The visual builder is the primary V1 authoring experience.
- Users should be able to switch between a visual pipeline editor and a structured text representation of the same pipeline definition.
- The two views must remain semantically aligned so that editing in one can be reflected in the other.
- The system should avoid introducing visual-only pipeline concepts that cannot be represented in the structured definition.
- Validation should run consistently regardless of whether the user edited the visual view or the structured view.

### 5. Property-Setting Constraint

- Any pipeline that configures a property must terminate in a `Property Set` pipeline step.
- The UI must validate this constraint before save or publish.
- The execution engine must also enforce this constraint defensively at runtime.

### 6. Reusable Components

- The system must support reusable pipeline step/component types.
- A reusable component must be configurable per usage instance.
- Reusable component definitions should be shared across pipelines without duplicating implementation logic.

### 7. Activity History

- Users must be able to view historical runs.
- A run detail view should show:
  - trigger source
  - input payload
  - pipeline used
  - per-stage status
  - per-step status
  - output summary
  - errors or warnings

## Reusable Component Example: Constrained Output Step

One example reusable step type is a component that constrains output to a defined set of values while still allowing AI-assisted suggestion behavior.

### Step Name

`Constrained Output`

### Configuration Options

- `Target Values`: array of allowed or preferred values
- `Allow Multiple`: whether multiple values may be selected
- `Suggestion Limit`: maximum number of new suggestions the model may add
- `Suggestion Eagerness`: integer from 0-5 controlling how readily the model suggests new values

### Behavioral Semantics

- At `0`, the model never suggests new values.
- At `1`, it suggests rarely and only when no existing value fits well.
- At `5`, it is very eager to propose new values up to the suggestion limit.

This step should be defined as a reusable primitive, not bespoke logic embedded in a single pipeline.

## First V1 UX Flow

The first productized UI flow should support the current Notion Place Inserter use case:

1. User logs in.
2. User connects Notion.
3. User opens `Data Targets`.
4. User selects a Notion database and exposed fields.
5. User opens `Triggers`.
6. User creates an authenticated HTTP trigger.
7. User opens `Pipelines`.
8. User creates or edits a pipeline that includes stages such as `research`.
9. User configures reusable pipeline steps and ends property-setting paths with `Property Set`.
10. An external caller hits the provisioned endpoint.
11. The system executes the pipeline and writes the result to Notion.
12. The user inspects the run in `Activity History`.

## UX Requirements

- The UI should make the product feel operational, not experimental.
- The UI should feel modern, minimal, and calm rather than visually busy.
- The target/trigger/pipeline model should be understandable without reading technical documentation.
- The system should clearly separate setup concerns from run-history concerns.
- The UI should guide users toward valid pipeline structures instead of relying on raw JSON editing.
- Validation errors should be shown before execution whenever possible.
- The visual design should prioritize clarity, whitespace, strong hierarchy, and restrained use of visual chrome.

## Technical Requirements

### Application Architecture

The architecture should support:

- frontend hosting
- backend API hosting
- background job execution
- persistent relational storage
- secret management
- future observability and operational tooling

The architecture must assume a split frontend/backend product with durable infrastructure. Phase 1 uses a hybrid model: Render hosts the runtime (API, worker, UI) while Supabase provides the platform/data plane (Postgres, queue, auth foundations). This keeps migration risk low while establishing durable primitives.

One hard requirement is that the platform layer (datastore, auth, queue) should be manageable in one ecosystem as much as possible. A platform in the category of Supabase is a strong directional fit for this requirement, because it reduces operational fragmentation and speeds up product iteration. Runtime hosting (API/worker/UI) may remain on Render in Phase 1; future migration of runtime to Supabase can be revisited after production metrics and cost review.

### Suggested Platform Capabilities

- Web application hosting for a frontend
- API/service hosting for backend execution and configuration APIs
- Postgres or equivalent managed relational database
- Background workers or job infrastructure for asynchronous executions
- Secure environment and secret management
- Built-in or tightly integrated authentication/user management
- Preferably one ecosystem that covers most or all of the stack rather than a fragmented multi-vendor setup

### Frontend Technology Direction

- The frontend should use modern, broadly adopted tooling with a strong ecosystem and many high-quality examples available.
- The frontend should avoid overly experimental or bleeding-edge choices that create unnecessary implementation or hiring risk.
- Prefer technologies that support building a modern and minimal UI efficiently while remaining stable and well documented.
- Component, styling, and state-management choices should favor maintainability and common industry patterns over novelty.

### Data Model Direction

Likely top-level entities:

- User
- Workspace or Tenant
- Integration Connection
- Data Target
- Target Field
- Trigger
- Pipeline Definition
- Stage Definition
- Pipeline Step Definition
- Pipeline Run
- Step Run
- Activity Event
- Invitation Code

User profile shape for Phase 2 should include a `user_type` enum (`ADMIN`, `STANDARD`, `BETA_TESTER`) and optional reference to the invitation code used during onboarding.

### Execution Model

- Trigger invocations should enqueue asynchronous runs.
- Pipeline execution should remain compatible with the existing staged pipeline architecture.
- Run state should be persisted so the UI can display progress and historical outcomes.

## Success Metrics

### Product Metrics

- Users can fully configure a Notion target and HTTP-triggered pipeline without code changes.
- Users can successfully authenticate and manage their own resources.
- Users can inspect run history and diagnose failures from the UI.
- Time to first configured pipeline is materially lower than with the current code-first setup.

### Technical Metrics

- Pipeline definitions persist reliably and can be re-run.
- Triggered runs are auditable end-to-end.
- Tenant isolation is maintained for stored configs and run data.
- The architecture can support adding a second target type without major model redesign.

## Risks

1. The UI builder could become too generic too early and slow down delivery.
2. A Notion-specific implementation could leak too deeply into core data models.
3. Auth, secrets, and tenant isolation add complexity that does not exist in the current single-user prototype.
4. Migration from a simple Render deployment to a fuller product stack increases operational complexity.
5. Pipeline configuration flexibility may create invalid or hard-to-debug execution graphs if guardrails are weak.

## Open Questions

1. Which end-to-end platform best balances speed and long-term maintainability for frontend, backend, workers, Postgres, and user management?
2. What secret-management approach should be used for stored integration credentials and trigger authentication material?

## Recommended Phasing

### Phase 1: Platform Migration

- Retain Render runtime (API and worker on Web Service, minimal UI on Static Site); migrate persistence and queue to Supabase
- Establish durable platform primitives (Postgres, pgmq queue, run history) in Supabase
- Preserve compatibility with the current execution engine where practical during the migration
- Minimize behavioral regressions while moving to the new platform foundation
- Stand up the API with an endpoint that behaves like the current `Render` endpoint
- Stand up a frontend using Vite, deployed to Render Static Site, with a single button that manually hits that endpoint
- Maintain frontend code in a separate repository from the backend/runtime repository
- Do not introduce user authentication in this phase

### Phase 2: Authentication and Segmentation

- Add authentication with basic sign-in/sign-up pages.
- Introduce user-based segmentation and ownership boundaries.
- Add a barebones public landing page with `Sign In / Sign Up` link in the upper-right.
- Keep the UI intentionally minimal at this stage.
- Add invite-code onboarding support and persistent invitation code records.
- Support user types (`ADMIN`, `STANDARD`, `BETA_TESTER`) with type assignment from claimed invite code.
- Add a manual script/CLI for operators to generate invitation codes.
- Redirect authenticated users to a dashboard landing page.
- Once logged in, the only user-facing action in the dashboard should be `Run Location Inserter (with dummy data)`.
- Do not introduce broader pipeline-management functionality yet.

### Phase 3: YAML-Backed Product Model

- Original scope for this phase: define the canonical product model and make triggers, targets, pipelines, stages, and steps load from local YAML instead of code.
- Standalone architecture document: [`technical/phase-3-yaml-backed-product-model/index.md`](../technical/phase-3-yaml-backed-product-model/)

- Define the core data model for triggers, data sources, targets, pipelines, stages, and pipeline steps
- Build logic to load triggers, data sources, targets, pipelines, and pipeline steps from a local YAML definition
- Preserve local YAML as the source of truth during this phase
- Use this phase to validate the generalized product abstractions before moving them into the datastore

### Phase 4: Datastore-Backed Definitions

- Move pipeline-related configuration from hardcoded local YAML loading to the datastore
- Load triggers, data sources, targets, pipelines, stages, and pipeline steps from the datastore itself
- Allow a logged-in user to view and edit a text representation of their pipeline definition as stored in the database
- Support updating that text representation and redeploying or reloading with the updated definition
- Keep the editing experience text-based in this phase rather than visual

### Phase 5: Visual Editing

- Add the rich visual pipeline editor
- Let users configure triggers, data sources, data targets, stages, pipelines, and pipeline steps through the UI
- Keep the visual editor aligned with the structured text representation so users can move between both views
- Deliver the intended modern, minimal, visual-first pipeline authoring experience

## Acceptance Criteria for This PRD

This PRD will be considered directionally successful if it guides implementation toward a product that:

1. Supports authenticated multi-user access.
2. Uses durable persistence, likely Postgres.
3. Provides a UI for targets, triggers, pipelines, account setup, and activity history.
4. Preserves `Stage`, `Pipeline`, and `PipelineStep` as the core execution abstractions.
5. Enforces that property-configuring flows end with `Property Set`.
6. Ships the current Notion Place Inserter as the first fully productized UI-backed workflow.
7. Leaves room for future non-Notion targets without major architectural rework.
