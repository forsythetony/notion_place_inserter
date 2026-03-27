-- Human-readable labels for step input fields (input_contract.fields.*.title) — pipeline editor INPUTS panel.
-- Idempotent: matches product_model/catalog/step_templates/step_template_property_set.yaml and
-- step_template_upload_image_to_notion.yaml.

UPDATE step_templates
SET input_contract = '{
  "fields": {
    "value": {
      "type": "any",
      "title": "Property value"
    }
  }
}'::jsonb
WHERE id = 'step_template_property_set';

UPDATE step_templates
SET input_contract = '{
  "fields": {
    "value": {
      "type": "string",
      "required": true,
      "title": "Image URL"
    }
  }
}'::jsonb
WHERE id = 'step_template_upload_image_to_notion';
