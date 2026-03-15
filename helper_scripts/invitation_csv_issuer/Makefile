# Invitation CSV issuer - issues invitations and creates users via backend API.
# Usage: make run-local CSV_PATH=input_actual.csv PASSWORD=... | make run-prod ...
#        make create-users-local CSV_PATH=... PASSWORD=... | make create-users-prod ...
.PHONY: help run run-local run-prod dry-run create-users-local create-users-prod create-users-dry-run

ENVS_DIR := ../../envs
CSV_PATH ?= input_actual.csv

help:
	@echo "Invitation CSV issuer - issues invitations and creates users from CSV via backend API."
	@echo ""
	@echo "Issue invitations:"
	@echo "  make run-local CSV_PATH=input_actual.csv PASSWORD=<password>  - Run with envs/local.env"
	@echo "  make run-prod  CSV_PATH=input_actual.csv PASSWORD=<password>  - Run with envs/prod.env"
	@echo "  make dry-run   CSV_PATH=input_actual.csv ENV=local|prod       - Validate CSV only (no API calls)"
	@echo ""
	@echo "Create users:"
	@echo "  make create-users-local CSV_PATH=input_actual.csv PASSWORD=<password>  - Run with envs/local.env"
	@echo "  make create-users-prod  CSV_PATH=input_actual.csv PASSWORD=<password>  - Run with envs/prod.env"
	@echo "  make create-users-dry-run CSV_PATH=input_actual.csv ENV=local|prod     - Validate CSV only"
	@echo ""
	@echo "Variables:"
	@echo "  CSV_PATH  - Path to CSV (default: input_actual.csv)"
	@echo "  PASSWORD  - Admin password (required for run/create-users)"
	@echo "  ENV       - local or prod for dry-run (default: local)"

run-local:
	@bash -c 'set -a && [ -f $(ENVS_DIR)/local.env ] && source $(ENVS_DIR)/local.env; set +a && \
		if [ -z "$(PASSWORD)" ]; then echo "Error: PASSWORD is required. Usage: make run-local PASSWORD=<password>"; exit 1; fi; \
		if [ ! -f "$(CSV_PATH)" ]; then echo "Error: CSV_PATH=$(CSV_PATH) not found"; exit 1; fi; \
		python main.py issue-invitations --csv-path "$(CSV_PATH)" --password "$(PASSWORD)" \
			--api-base-url "$${BASE_URL}" --supabase-url "$${SUPABASE_URL}"'

run-prod:
	@bash -c 'set -a && [ -f $(ENVS_DIR)/prod.env ] && source $(ENVS_DIR)/prod.env; set +a && \
		if [ -z "$(PASSWORD)" ]; then echo "Error: PASSWORD is required. Usage: make run-prod PASSWORD=<password>"; exit 1; fi; \
		if [ ! -f "$(CSV_PATH)" ]; then echo "Error: CSV_PATH=$(CSV_PATH) not found"; exit 1; fi; \
		python main.py issue-invitations --csv-path "$(CSV_PATH)" --password "$(PASSWORD)" \
			--api-base-url "$${BASE_URL}" --supabase-url "$${SUPABASE_URL}"'

# Alias: run = run-local
run: run-local

ENV ?= local
dry-run:
	@bash -c 'set -a && \
		if [ "$(ENV)" = "prod" ]; then [ -f $(ENVS_DIR)/prod.env ] && source $(ENVS_DIR)/prod.env; \
		else [ -f $(ENVS_DIR)/local.env ] && source $(ENVS_DIR)/local.env; fi; set +a && \
		python main.py issue-invitations --csv-path "$(CSV_PATH)" --api-base-url "$${BASE_URL}" --supabase-url "$${SUPABASE_URL}" --dry-run'

create-users-local:
	@bash -c 'set -a && [ -f $(ENVS_DIR)/local.env ] && source $(ENVS_DIR)/local.env; set +a && \
		if [ -z "$(PASSWORD)" ]; then echo "Error: PASSWORD is required. Usage: make create-users-local PASSWORD=<password>"; exit 1; fi; \
		if [ ! -f "$(CSV_PATH)" ]; then echo "Error: CSV_PATH=$(CSV_PATH) not found"; exit 1; fi; \
		python main.py create-users --csv-path "$(CSV_PATH)" --password "$(PASSWORD)" \
			--api-base-url "$${BASE_URL}" --supabase-url "$${SUPABASE_URL}"'

create-users-prod:
	@bash -c 'set -a && [ -f $(ENVS_DIR)/prod.env ] && source $(ENVS_DIR)/prod.env; set +a && \
		if [ -z "$(PASSWORD)" ]; then echo "Error: PASSWORD is required. Usage: make create-users-prod PASSWORD=<password>"; exit 1; fi; \
		if [ ! -f "$(CSV_PATH)" ]; then echo "Error: CSV_PATH=$(CSV_PATH) not found"; exit 1; fi; \
		python main.py create-users --csv-path "$(CSV_PATH)" --password "$(PASSWORD)" \
			--api-base-url "$${BASE_URL}" --supabase-url "$${SUPABASE_URL}"'

create-users-dry-run:
	@bash -c 'set -a && \
		if [ "$(ENV)" = "prod" ]; then [ -f $(ENVS_DIR)/prod.env ] && source $(ENVS_DIR)/prod.env; \
		else [ -f $(ENVS_DIR)/local.env ] && source $(ENVS_DIR)/local.env; fi; set +a && \
		python main.py create-users --csv-path "$(CSV_PATH)" --api-base-url "$${BASE_URL}" --supabase-url "$${SUPABASE_URL}" --dry-run'
