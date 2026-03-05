.PHONY: install run run-local test test-api notion-pull

PORT ?= 8000
SECRET ?= dev-secret
BASE_URL ?= http://localhost:8000

export BASE_URL SECRET

install:
	pip install -r requirements.txt

run:
	@bash -c 'set -a && [ -f envs/local.env ] && source envs/local.env; set +a && . env/bin/activate 2>/dev/null || true; PORT=$(PORT) secret=$(SECRET) uvicorn app.main:app --host 0.0.0.0 --port $(PORT)'

rerun: install run

run-local:
	@bash -c 'set -a && source envs/local.env && set +a && uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000}'

test:
	@echo "Testing without auth (expect 401)..."
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:$(PORT)/
	@echo "Testing with auth (expect 200)..."
	@curl -s -H "Authorization: $(SECRET)" http://localhost:$(PORT)/

test-api:
	python -m pytest http-test/ -v

test-api-%:
	@bash -c 'set -a && source envs/$*.env && set +a && python -m pytest http-test/ -v'

notion-pull:
	python scripts/notion_puller/main.py
