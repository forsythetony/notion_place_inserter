-- Add query_schema to step_templates for schema-aware Optimize Input
ALTER TABLE step_templates ADD COLUMN IF NOT EXISTS query_schema jsonb DEFAULT NULL;
