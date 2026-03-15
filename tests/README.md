# Tests

## Isolated Notion Write (Live Connector)

Debug the Notion write step in isolation without running the full pipeline.

**Env vars:**
- `NOTION_API_KEY` — Notion integration token
- `NOTION_TEST_DATA_SOURCE_ID` — Target database/data source ID (e.g. `9592d56b-899e-440e-9073-b2f0768669ad`)

**Run:**
```bash
pytest tests/test_notion_write_step_live.py -m live_notion -q
```

On success, the test creates a page and prints `page_id`. On failure, the raw Notion API error is surfaced.
