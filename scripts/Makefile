# Convenience targets for scripts in this repo. Calls run from the repo root so
# paths like envs/local.env match the main Makefile.
#
# From repo root (no args uses default query: stone arch bridge Minneapolis):
#   make -C scripts probe-google-places
#   make -C scripts probe-google-places QUERY="Cafe Boston"
#   make -C scripts probe-google-places ENV_FILE=envs/prod.env DETAILS=1
#
# From this directory:
#   make probe-google-places

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

.PHONY: help probe-google-places

ENV_FILE ?= envs/local.env
DETAILS ?=
QUERY ?= stone arch bridge Minneapolis

help:
	@echo "Google Places integration probe (raw searchText / optional placeDetails JSON)."
	@echo "Usage: make probe-google-places [QUERY=\"text\"] [ENV_FILE=envs/prod.env] [DETAILS=1]"
	@echo "Default QUERY: stone arch bridge Minneapolis. From repo root: make -C scripts probe-google-places"

probe-google-places:
	@cd "$(ROOT)" && python scripts/integration_probes/google_places_probe.py \
		--env-file "$(ENV_FILE)" $(if $(DETAILS),--details,) "$(QUERY)"
