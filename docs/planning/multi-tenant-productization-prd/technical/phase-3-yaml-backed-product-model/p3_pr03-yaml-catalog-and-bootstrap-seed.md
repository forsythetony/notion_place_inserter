# p3_pr03 - YAML Catalog and Bootstrap Seed

**Status:** Complete (2026-03-14)

## Objective

Implement YAML repository implementations and seed the catalog and bootstrap content: connector templates, target templates, step templates, and the `Notion Place Inserter` job starter for authenticated users.

## Scope

- Implement YAML repository classes for catalog entities: `YamlConnectorTemplateRepository`, `YamlTargetTemplateRepository`, `YamlStepTemplateRepository`
- Add checked-in YAML files in `product_model/catalog/` for: `notion_oauth_workspace`, `google_places_api`, `claude_api`; `notion_database` target template; all seven step templates (Optimize Input, Google Places Lookup, AI Constrain Values, Cache Set, Cache Get, Property Set, Extract Target Property Options)
- Add `product_model/bootstrap/jobs/notion_place_inserter.yaml` as the shared starter job definition
- Implement `YamlJobRepository` with support for loading from bootstrap and tenant paths
- Loader that materializes the `Notion Place Inserter` template for authenticated users (from bootstrap, not tenant)

## Expected changes

- YAML repository implementations for catalog and job loading
- New YAML files in `product_model/catalog/` and `product_model/bootstrap/jobs/`
- Bootstrap loader used when serving job definitions to signed-in users

## Acceptance criteria

- Catalog YAML files parse into domain objects correctly
- `Notion Place Inserter` bootstrap job loads and matches architecture doc example structure
- Every signed-in user receives the same starter definition from bundled YAML
- Catalog and bootstrap paths are read-only; tenant paths (when used) support ephemeral writes

## Out of scope

- Tenant-scoped YAML writes (beyond loader behavior)
- Validation of job/stage/pipeline/step structure
- Execution or trigger wiring

## Dependencies

- Requires p3_pr01 (domain entities) and p3_pr02 (repository interfaces and layout).

---

## Manual validation steps (after implementation)

1. Run loader for a mock authenticated user and confirm `Notion Place Inserter` job is returned.
2. Inspect catalog YAML files and confirm they parse without error.
3. Confirm bootstrap job structure matches architecture doc (stages, pipelines, steps, bindings).

## Verification checklist

- [x] Catalog YAML files parse into domain objects.
- [x] Bootstrap `Notion Place Inserter` loads correctly.
- [x] Loader returns starter job for authenticated users.
- [x] Catalog and bootstrap are read-only; tenant layout supports ephemeral writes.
