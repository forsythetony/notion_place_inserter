.PHONY: install run test test-api notion-pull

PORT ?= 8000
SECRET ?= dev-secret
BASE_URL ?= http://localhost:8000

export BASE_URL SECRET

install:
	pip install -r requirements.txt

run:
	PORT=$(PORT) secret=$(SECRET) uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

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
