# p3_pr07 - Trigger, Target, and Schema Services

## Objective

Wire `TriggerService`, `TargetService`, and `SchemaSyncService` to YAML repositories so triggers, targets, and schema snapshots are persisted and resolvable from definitions.

## Scope

- Implement `YamlTriggerRepository`, `YamlTargetRepository`, `YamlTargetSchemaRepository`, `YamlConnectorInstanceRepository`
- Add `TriggerService` for trigger CRUD and resolution by path/owner
- Add `TargetService` for target CRUD and resolution; support `active_schema_snapshot_id`
- Add `SchemaSyncService` for fetching live schema from connector, creating `TargetSchemaSnapshot`, and attaching to `DataTarget`
- Wire HTTP trigger definition to route registration: `POST /triggers/{user_id}/{path}` resolves trigger by (path, owner_user_id) and dispatches job
- Ensure connector instances use `secret_ref` (not plaintext); support env/local alias in Phase 3
- Support global target-level property rules (`property_rules` on `DataTarget`)

## Expected changes

- YAML repository implementations for triggers, targets, schema snapshots, connector instances
- `TriggerService`, `TargetService`, `SchemaSyncService` implementations
- Single route `POST /triggers/{user_id}/{path}` that resolves trigger by path and owner_user_id, then dispatches job
- Schema fetch and snapshot persistence flow

## Acceptance criteria

- Triggers are loadable from YAML and resolvable by path and owner
- Targets are loadable and reference connector instances and active schema snapshots
- Schema sync fetches from Notion (or connector), creates snapshot, and updates target
- `POST /triggers/{user_id}/{path}` resolves trigger by (path, user_id) and dispatches job
- Connector instances reference secrets via `secret_ref`, not plaintext

## Out of scope

- Full trigger CRUD API (if not needed for Phase 3 bootstrap)
- Vault/secret backend (Phase 4); Phase 3 uses env/local alias
- Per-account secret management (Phase 4); Phase 3 uses shared SECRET for all users (tech debt)

## Dependencies

- Requires p3_pr01 through p3_pr04 (p3_pr07 precedes p3_pr05 in execution order).

---

## Manual validation steps (after implementation)

1. Load a trigger definition from YAML and confirm it resolves to a job.
2. Create or load a target with connector instance; run schema sync and confirm snapshot is created and attached.
3. Invoke `POST /triggers/{user_id}/{path}` (e.g. `/triggers/bootstrap/locations`) and confirm job is dispatched.
4. Confirm connector instance uses secret_ref, not raw credentials in YAML.

## Verification checklist

- [ ] Triggers load and resolve by path/owner.
- [ ] Targets load and reference schema snapshots.
- [ ] Schema sync creates and attaches snapshots.
- [ ] `POST /triggers/{user_id}/{path}` resolves trigger and dispatches job.
- [ ] Secrets use secret_ref only.
