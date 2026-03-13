.PHONY: help install run run-local run-dry-run run-debug-run kill-port clear-logs test test-api test-icon test-google-places test-random-location test-locations test-remote notion-pull tag supabase-start supabase-stop supabase-status supabase-reset supabase-migration-new supabase-login supabase-link supabase-db-push supabase-deploy

PORT ?= 8000
SECRET ?= dev-secret
BASE_URL ?= http://localhost:8000
KEYWORDS ?= stone arch bridge minneapolis
REMOTE_BASE_URL ?=
REMOTE_SECRET ?=
LOG_LEVEL ?= DEBUG
SUPABASE_PROJECT_REF ?= ngwcqykrmlwlythbkmwn
# Override env-imported LOG_LEVEL so Makefile default wins (env can otherwise force INFO)
ifeq ($(origin LOG_LEVEL),environment)
  override LOG_LEVEL := DEBUG
endif

export BASE_URL SECRET LOG_LEVEL

help:
	@echo "Available commands (LOG_LEVEL=$(LOG_LEVEL), override with make run LOG_LEVEL=DEBUG):"
	@echo "  make help              - List all commands with descriptions"
	@echo "  make install           - Install Python dependencies"
	@echo "  make run               - Start the server (loads envs/local.env if present)"
	@echo "  make rerun             - Install dependencies and start the server"
	@echo "  make run-local         - Start the server with envs/local.env"
	@echo "  make run-dry-run       - Start the server in dry-run mode (no Notion writes)"
	@echo "  make run-debug-run     - Same as run-dry-run with LOG_LEVEL=DEBUG forced"
	@echo "  make run-async         - Start the server with async locations (default)"
	@echo "  make run-sync          - Start the server with sync locations (LOCATIONS_ASYNC_ENABLED=0)"
	@echo "  make kill-port         - Kill process on port $(PORT)"
	@echo "  make clear-logs        - Remove log files from logs/"
	@echo "  make test              - Quick smoke test (curl health check)"
	@echo "  make test-api          - Run pytest (http-test + tests, excludes locations integration)"
	@echo "  make test-api-<env>    - Run pytest with specific env (e.g. test-api-local)"
	@echo "  make test-icon         - Run icon/Freepik pipeline and service tests"
	@echo "  make test-google-places - Test Google Places search (server must be running)"
	@echo "  make test-random-location - Test random location endpoint"
	@echo "  make test-locations    - Test locations API with KEYWORDS (default: stone arch bridge minneapolis)"
	@echo "  make test-remote REMOTE_BASE_URL=<https://...> REMOTE_SECRET=<secret> - Smoke test remote app and /locations enqueue"
	@echo "  make test-whatsapp     - Send a test WhatsApp message to WHATSAPP_STATUS_RECIPIENT_DEFAULT"
	@echo "  make notion-pull       - Run Notion puller script"
	@echo "  make tag VERSION=vX.Y.Z - Create and push an annotated git tag (e.g. VERSION=v1.0.0)"
	@echo ""
	@echo "Supabase (local stack, migrations):"
	@echo "  make supabase-start    - Start local Supabase stack (Docker required)"
	@echo "  make supabase-stop     - Stop local Supabase stack"
	@echo "  make supabase-status   - Show Supabase stack status"
	@echo "  make supabase-reset    - Reset DB and reapply all migrations"
	@echo "  make supabase-migration-new NAME=<name> - Create new migration file"
	@echo ""
	@echo "Supabase (remote project deploy):"
	@echo "  make supabase-login    - Log in to Supabase CLI"
	@echo "  make supabase-link     - Link CLI to remote project (SUPABASE_PROJECT_REF=$(SUPABASE_PROJECT_REF))"
	@echo "  make supabase-db-push  - Push local migrations to linked remote project"
	@echo "  make supabase-deploy   - Link project and push migrations to remote"

install:
	pip install -r requirements.txt

run:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) LOG_LEVEL=$(LOG_LEVEL) uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

rerun: install run

run-local:
	@bash -c 'set -a && source envs/local.env && set +a && LOG_LEVEL=$${LOG_LEVEL:-$(LOG_LEVEL)} uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000}'

run-dry-run:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; DRY_RUN=1; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) LOG_LEVEL=$(LOG_LEVEL) DRY_RUN=1 uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

run-debug-run:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; DRY_RUN=1; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) LOG_LEVEL=DEBUG DRY_RUN=1 uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

run-async:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; LOCATIONS_ASYNC_ENABLED=1; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) LOG_LEVEL=$(LOG_LEVEL) LOCATIONS_ASYNC_ENABLED=1 uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

run-sync:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; LOCATIONS_ASYNC_ENABLED=0; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) LOG_LEVEL=$(LOG_LEVEL) LOCATIONS_ASYNC_ENABLED=0 uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

kill-port:
	@bash -c 'pid=$$(lsof -ti:$(PORT)); if [ -n "$$pid" ]; then kill -9 $$pid && echo "Killed process on port $(PORT)"; else echo "Nothing running on port $(PORT)"; fi'

clear-logs:
	@rm -f logs/*.log && echo "Cleared logs/" || true

test:
	@echo "Testing without auth (expect 401)..."
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:$(PORT)/
	@echo "Testing with auth (expect 200)..."
	@curl -s -H "Authorization: $(SECRET)" http://localhost:$(PORT)/

test-api:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && LOG_LEVEL=$(LOG_LEVEL) python -m pytest http-test/ tests/ -v --ignore=tests/test_locations_integration.py'

test-icon:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && LOG_LEVEL=$(LOG_LEVEL) python -m pytest tests/test_cover_icon_pipeline.py tests/test_freepik_service.py tests/test_claude_service_option_selection.py tests/test_dry_run_renderer.py -v'

test-google-places:
	@curl -s -H "Authorization: $(SECRET)" "http://localhost:$(PORT)/test/googlePlacesSearch?query=pizza+in+new+york"

test-random-location:
	@curl -s -X POST -H "Authorization: $(SECRET)" "http://localhost:$(PORT)/test/randomLocation"

test-locations:
	@curl -s -X POST -H "Authorization: $(SECRET)" -H "Content-Type: application/json" \
		-d '{"keywords":"$(KEYWORDS)"}' "$(BASE_URL)/locations"

test-remote:
	@bash -c 'if [ -z "$(REMOTE_BASE_URL)" ]; then echo "Usage: make test-remote REMOTE_BASE_URL=<https://...> REMOTE_SECRET=<secret> [KEYWORDS=\"...\"]"; exit 1; fi; \
	if [ -z "$(REMOTE_SECRET)" ]; then echo "Usage: make test-remote REMOTE_BASE_URL=<https://...> REMOTE_SECRET=<secret> [KEYWORDS=\"...\"]"; exit 1; fi; \
	echo "Testing remote root without auth (expect 401)..."; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" "$(REMOTE_BASE_URL)/"; \
	echo "Testing remote root with auth (expect 200)..."; \
	curl -s -o /dev/null -w "HTTP %{http_code}\n" -H "Authorization: $(REMOTE_SECRET)" "$(REMOTE_BASE_URL)/"; \
	echo "Testing remote /locations enqueue (expect 200 accepted in async mode)..."; \
	curl -s -X POST -H "Authorization: $(REMOTE_SECRET)" -H "Content-Type: application/json" \
		-d "{\"keywords\":\"$(KEYWORDS)\"}" "$(REMOTE_BASE_URL)/locations"'

test-whatsapp:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && python scripts/test_whatsapp.py'

test-api-%:
	@bash -c 'set -a && source envs/$*.env && set +a && LOG_LEVEL=$${LOG_LEVEL:-$(LOG_LEVEL)} python -m pytest http-test/ -v'

notion-pull:
	LOG_LEVEL=$(LOG_LEVEL) python scripts/notion_puller/main.py

tag:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make tag VERSION=vX.Y.Z (e.g. VERSION=v1.0.0)"; exit 1; fi; \
	if ! echo "$(VERSION)" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$$'; then echo "Error: VERSION must match semantic versioning (e.g. v1.0.0)"; exit 1; fi; \
	git tag -a "$(VERSION)" -m "Release $(VERSION)" && git push origin "$(VERSION)"

# Supabase local stack and migration workflow
supabase-start:
	supabase start

supabase-stop:
	supabase stop

supabase-status:
	supabase status

supabase-reset:
	supabase db reset

supabase-migration-new:
	@if [ -z "$(NAME)" ]; then echo "Usage: make supabase-migration-new NAME=<migration_name> (e.g. NAME=add_users_table)"; exit 1; fi; \
	supabase migration new "$(NAME)"

supabase-login:
	supabase login

supabase-link:
	@if [ -z "$(SUPABASE_PROJECT_REF)" ]; then echo "Usage: make supabase-link SUPABASE_PROJECT_REF=<project_ref>"; exit 1; fi; \
	supabase link --project-ref "$(SUPABASE_PROJECT_REF)"

supabase-db-push:
	supabase db push

supabase-deploy: supabase-link supabase-db-push
