-- Job (and other entity) status: add `disabled` for trigger-off without archive.
ALTER TYPE entity_status_enum ADD VALUE 'disabled';
