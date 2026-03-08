.PHONY: help install run run-local run-dry-run kill-port test test-api test-icon test-google-places test-random-location test-locations notion-pull

PORT ?= 8000
SECRET ?= dev-secret
BASE_URL ?= http://localhost:8000
KEYWORDS ?= stone arch bridge minneapolis

export BASE_URL SECRET

help:
	@echo "Available commands:"
	@echo "  make help              - List all commands with descriptions"
	@echo "  make install           - Install Python dependencies"
	@echo "  make run               - Start the server (loads envs/local.env if present)"
	@echo "  make rerun             - Install dependencies and start the server"
	@echo "  make run-local         - Start the server with envs/local.env"
	@echo "  make run-dry-run       - Start the server in dry-run mode (no Notion writes)"
	@echo "  make kill-port         - Kill process on port $(PORT)"
	@echo "  make test              - Quick smoke test (curl health check)"
	@echo "  make test-api          - Run pytest (http-test + tests, excludes locations integration)"
	@echo "  make test-api-<env>    - Run pytest with specific env (e.g. test-api-local)"
	@echo "  make test-icon         - Run icon/Freepik pipeline and service tests"
	@echo "  make test-google-places - Test Google Places search (server must be running)"
	@echo "  make test-random-location - Test random location endpoint"
	@echo "  make test-locations    - Test locations API with KEYWORDS (default: stone arch bridge minneapolis)"
	@echo "  make notion-pull       - Run Notion puller script"

install:
	pip install -r requirements.txt

run:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) secret=$(SECRET) uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

rerun: install run

run-local:
	@bash -c 'set -a && source envs/local.env && set +a && uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000}'

run-dry-run:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; DRY_RUN=1; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) secret=$(SECRET) DRY_RUN=1 uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

kill-port:
	@bash -c 'pid=$$(lsof -ti:$(PORT)); if [ -n "$$pid" ]; then kill -9 $$pid && echo "Killed process on port $(PORT)"; else echo "Nothing running on port $(PORT)"; fi'

test:
	@echo "Testing without auth (expect 401)..."
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:$(PORT)/
	@echo "Testing with auth (expect 200)..."
	@curl -s -H "Authorization: $(SECRET)" http://localhost:$(PORT)/

test-api:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && python -m pytest http-test/ tests/ -v --ignore=tests/test_locations_integration.py'

test-icon:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && python -m pytest tests/test_cover_icon_pipeline.py tests/test_freepik_service.py tests/test_claude_service_option_selection.py tests/test_dry_run_renderer.py -v'

test-google-places:
	@curl -s -H "Authorization: $(SECRET)" "http://localhost:$(PORT)/test/googlePlacesSearch?query=pizza+in+new+york"

test-random-location:
	@curl -s -X POST -H "Authorization: $(SECRET)" "http://localhost:$(PORT)/test/randomLocation"

test-locations:
	@curl -s -X POST -H "Authorization: $(SECRET)" -H "Content-Type: application/json" \
		-d '{"keywords":"$(KEYWORDS)"}' "http://localhost:$(PORT)/locations"

test-api-%:
	@bash -c 'set -a && source envs/$*.env && set +a && python -m pytest http-test/ -v'

notion-pull:
	python scripts/notion_puller/main.py
