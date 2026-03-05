.PHONY: install run test

PORT ?= 8000
SECRET ?= dev-secret

install:
	pip install -r requirements.txt

run:
	PORT=$(PORT) secret=$(SECRET) uvicorn app.main:app --host 0.0.0.0 --port $(PORT)

test:
	@echo "Testing without auth (expect 401)..."
	@curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost:$(PORT)/
	@echo "Testing with auth (expect 200)..."
	@curl -s -H "Authorization: $(SECRET)" http://localhost:$(PORT)/
