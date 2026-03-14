# p3_pr02 - Repository Interfaces and YAML Layout

## Objective

Define repository interfaces (protocols/abstract bases) and the YAML file layout contract so storage adapters have a clear, Phase-4-ready contract.

## Scope

- Define repository interfaces for: `ConnectorTemplateRepository`, `ConnectorInstanceRepository`, `TargetTemplateRepository`, `TargetRepository`, `TargetSchemaRepository`, `TriggerRepository`, `JobRepository`, `StepTemplateRepository`, `RunRepository`, `AppConfigRepository`
- Document the on-disk YAML layout: `product_model/bootstrap/`, `product_model/catalog/`, `product_model/tenants/<owner_user_id>/`
- Define interface methods (e.g., `get_by_id`, `list_by_owner`, `save`, `delete`) without implementation
- Ensure interfaces are storage-agnostic so Phase 4 can swap in Postgres implementations

## Expected changes

- New repository protocol/abstract module(s)
- Layout documentation or constants for paths (`bootstrap/jobs/`, `catalog/connector_templates/`, `catalog/step_templates/`, `tenants/<id>/connector_instances/`, etc.)
- No YAML read/write implementation yet

## Acceptance criteria

- All repository interfaces are defined with method signatures
- YAML layout matches architecture doc: bootstrap, catalog, tenants structure
- Interfaces do not reference YAML or Postgres; they operate on domain objects only
- Layout is documented so implementers know where to read/write files

## Out of scope

- YAML repository implementations
- Actual file I/O
- Service layer wiring

## Dependencies

- Requires p3_pr01 (domain entities).

---

## Manual validation steps (after implementation)

1. Import repository protocols and confirm they define expected methods.
2. Verify layout constants/paths align with architecture doc.
3. Confirm no file system or database imports in interface definitions.

## Verification checklist

- [ ] All repository interfaces are defined with correct method signatures.
- [ ] YAML layout matches architecture doc.
- [ ] Interfaces are storage-agnostic.
- [ ] Layout is documented for implementers.
