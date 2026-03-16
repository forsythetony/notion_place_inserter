# Test Notion OAuth Database Access

A small Python script to validate OAuth token access to Notion data sources. Use it to diagnose "Could not find data_source" errors and verify that databases are shared with your integration.

## Setup

1. **Get an OAuth token**

   - Sign in to the app and connect your Notion workspace via the Connections flow.
   - Or use a token from your OAuth callback / token refresh flow for testing.

2. **Configure the token**

   Add to `envs/local.env`:

   ```bash
   NOTION_OAUTH_TEST_TOKEN=your_oauth_access_token_here
   ```

   Or pass it via `--token` (see Usage).

3. **Install dependencies**

   The script uses packages from the main project:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

### List accessible data sources (default)

```bash
# Using token from envs/local.env
python scripts/test_notion_oauth_db.py

# With explicit token
python scripts/test_notion_oauth_db.py --token "your_oauth_token"

# Via Makefile (sources envs/local.env)
make test-notion-oauth-db
```

### Test a specific data source

Use when you see a "Could not find data_source with ID: ..." error in worker logs:

```bash
# Test the failing data source ID from the error
python scripts/test_notion_oauth_db.py --data-source-id 1e2a5cd4-f107-490f-9b7a-4af865fd1beb

# Or with token from env
make test-notion-oauth-db DATABASE_ID_ARG="--data-source-id 1e2a5cd4-f107-490f-9b7a-4af865fd1beb"
```

### List accessible pages

```bash
# List all pages shared with the integration
python scripts/test_notion_oauth_db.py --list-pages

# List both data sources and pages
python scripts/test_notion_oauth_db.py --list-all
```

### Search by title

```bash
# Filter results by title (works with --list-only, --list-pages, --list-all)
python scripts/test_notion_oauth_db.py --list-pages --query "Places"
python scripts/test_notion_oauth_db.py --query "Locations"
```

### Save to CSV (gitignored)

Results are saved to `temp/` (already gitignored). Use `--fetch-titles` for complete metadata (parent_type, url, timestamps, etc.):

```bash
python scripts/test_notion_oauth_db.py --list-pages --output-csv
python scripts/test_notion_oauth_db.py --list-all --fetch-titles --output-csv
```

CSV columns: `type`, `id`, `display_name`, `parent_type`, `parent_id`, `created_time`, `last_edited_time`, `url`, `public_url`, `in_trash`, `database_parent_type`, `database_parent_id`

### Fetch full titles (when search returns partial)

If display names show as IDs, the search API may have returned partial objects. Use `--fetch-titles` to retrieve each item for proper titles (slower, more API calls):

```bash
python scripts/test_notion_oauth_db.py --list-pages --fetch-titles --output-csv
```

### Verbose output

```bash
python scripts/test_notion_oauth_db.py --verbose
python scripts/test_notion_oauth_db.py --data-source-id <id> -v
```

## Environment

| Variable                 | Required | Description                                      |
|--------------------------|----------|--------------------------------------------------|
| `NOTION_OAUTH_TEST_TOKEN` | No*      | OAuth access token. Use `--token` if not set.   |

\* Either `NOTION_OAUTH_TEST_TOKEN` or `--token` must be provided.

## Interpreting results

- **SUCCESS** — Token has access to the data source. If the worker still fails, the issue may be token scope, workspace mismatch, or a different data source ID in the pipeline config.
- **Notion API error (object_not_found)** — The database is not shared with your integration. In Notion: open the database → Share → invite "Place Inserter" (or your integration name).
- **No data sources found** — Token may be invalid, expired, or the workspace has no databases shared with the integration.

## Makefile

Add to your `Makefile` (optional):

```makefile
test-notion-oauth-db:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && \
		python scripts/test_notion_oauth_db.py $(DATABASE_ID_ARG)'
```

Usage: `make test-notion-oauth-db` or `make test-notion-oauth-db DATABASE_ID_ARG="--data-source-id <id>"`
