# p3_pr07 - Trigger, Target, and Schema Services

## Objective

Wire `TriggerService`, `TargetService`, and `SchemaSyncService` to YAML repositories so triggers, targets, and schema snapshots are persisted and resolvable from definitions.

## Scope

- Implement `YamlTriggerRepository`, `YamlTargetRepository`, `YamlTargetSchemaRepository`, `YamlConnectorInstanceRepository`
- Add `TriggerService` for trigger CRUD and resolution by path/owner
- Add `TargetService` for target CRUD and resolution; support `active_schema_snapshot_id`
- Add `SchemaSyncService` for fetching live schema from connector, creating `TargetSchemaSnapshot`, and attaching to `DataTarget`
- Wire HTTP trigger definition to route registration (e.g., trigger path -> job dispatch)
- Ensure connector instances use `secret_ref` (not plaintext); support env/local alias in Phase 3
- Support global target-level property rules (`property_rules` on `DataTarget`)

## Expected changes

- YAML repository implementations for triggers, targets, schema snapshots, connector instances
- `TriggerService`, `TargetService`, `SchemaSyncService` implementations
- Route registration driven by trigger definitions (or equivalent)
- Schema fetch and snapshot persistence flow

## Acceptance criteria

- Triggers are loadable from YAML and resolvable by path and owner
- Targets are loadable and reference connector instances and active schema snapshots
- Schema sync fetches from Notion (or connector), creates snapshot, and updates target
- Trigger path maps to job dispatch
- Connector instances reference secrets via `secret_ref`, not plaintext

## Out of scope

- Full trigger CRUD API (if not needed for Phase 3 bootstrap)
- Vault/secret backend (Phase 4); Phase 3 uses env/local alias

## Dependencies

- Requires p3_pr01 through p3_pr04 (p3_pr07 precedes p3_pr05 in execution order).

---

## Manual validation steps (after implementation)

1. Load a trigger definition from YAML and confirm it resolves to a job.
2. Create or load a target with connector instance; run schema sync and confirm snapshot is created and attached.
3. Invoke trigger by path and confirm job is dispatched.
4. Confirm connector instance uses secret_ref, not raw credentials in YAML.

## Verification checklist

- [ ] Triggers load and resolve by path/owner.
- [ ] Targets load and reference schema snapshots.
- [ ] Schema sync creates and attaches snapshots.
- [ ] Trigger path maps to job dispatch.
- [ ] Secrets use secret_ref only.
