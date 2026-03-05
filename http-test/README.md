# HTTP API Tests (Tavern)

Tavern-style API tests for the Hello World FastAPI application.

## Prerequisites

- Server running locally (`make run` from project root) or a deployed instance
- Dependencies installed (`pip install -r requirements.txt`)

## Running Tests

From the project root:

```bash
# Run Tavern API tests (server must be running on localhost:8000)
make test-api

# Or directly with pytest
pytest http-test/ -v
```

## Configuration

Edit `config.tavern.yaml` to change the target URL or secret:

- `base_url`: API base URL (default: `http://localhost:8000`)
- `secret`: Authorization value for the `Authorization` header (default: `dev-secret`)

For a deployed Render instance, update `base_url` to your service URL and `secret` to the value from the Render Dashboard Environment tab.
