-- Catalog step templates (e.g. cache_get) may use status `deprecated` in YAML seeds.
ALTER TYPE entity_status_enum ADD VALUE 'deprecated';
