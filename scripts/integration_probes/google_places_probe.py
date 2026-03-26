#!/usr/bin/env python3
"""Print raw JSON from Google Places API (New): searchText and optionally placeDetails.

Uses the same HTTP client as production (``app.services.google_places_service.GooglePlacesService``).

Run from repo root (no args uses a default Minneapolis query):

    python scripts/integration_probes/google_places_probe.py
    python scripts/integration_probes/google_places_probe.py "Cafe Name Boston"
    python scripts/integration_probes/google_places_probe.py "query" --details
    python scripts/integration_probes/google_places_probe.py --env-file envs/prod.env "query" --details
    python scripts/integration_probes/google_places_probe.py --details-only --place-id places/ChIJ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PROBE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_PROBE_DIR))

import env_load  # noqa: E402
from app.services.google_places_service import GooglePlacesService  # noqa: E402
from loguru import logger  # noqa: E402

DEFAULT_QUERY = "stone arch bridge Minneapolis"


def _print_section(title: str) -> None:
    print(title)


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe Google Places API; print raw JSON to stdout.")
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help=f"Text query for searchText (textQuery). Default: {DEFAULT_QUERY!r}. Not used with --details-only.",
    )
    parser.add_argument(
        "--env-file",
        default="envs/local.env",
        help="Env file path (relative to repo root or absolute). Default: envs/local.env",
    )
    parser.add_argument(
        "--details",
        action="store_true",
        help="After search, also fetch placeDetails for the first result and print raw JSON.",
    )
    parser.add_argument(
        "--details-only",
        action="store_true",
        help="Skip search; fetch placeDetails only (requires --place-id).",
    )
    parser.add_argument(
        "--place-id",
        default=None,
        help="Place resource name for details-only, or implied when chaining from search.",
    )
    args = parser.parse_args()

    loaded = env_load.load_probe_env(args.env_file)
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{message}")
    logger.info("Loaded env file: {}", loaded)

    api_key = (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if not api_key:
        logger.error("GOOGLE_PLACES_API_KEY is missing after loading {}", loaded)
        sys.exit(1)

    svc = GooglePlacesService(api_key=api_key)

    if args.details_only:
        place_id = (args.place_id or "").strip()
        if not place_id:
            parser.error("--details-only requires --place-id")
        result = svc.get_place_details(place_id, return_raw_response=True)
        if not isinstance(result, tuple):
            parser.error("unexpected return from get_place_details")
        _, raw_details = result
        _print_section("=== placeDetails ===")
        _print_json(raw_details)
        return

    query = (args.query or DEFAULT_QUERY).strip()
    if not query:
        parser.error("query text is empty")

    search_result = svc.search_places(query, return_raw_response=True)
    if not isinstance(search_result, tuple):
        parser.error("unexpected return from search_places")
    _, raw_search = search_result

    _print_section("=== searchText ===")
    _print_json(raw_search)

    if not args.details:
        return

    places = raw_search.get("places") if isinstance(raw_search, dict) else None
    first = places[0] if isinstance(places, list) and places else None
    pid = None
    if isinstance(first, dict):
        pid = first.get("id")
    pid = (pid or args.place_id or "").strip()
    if not pid:
        logger.info("No place id for --details; skipping placeDetails call.")
        return

    details_tuple = svc.get_place_details(pid, return_raw_response=True)
    if not isinstance(details_tuple, tuple):
        return
    _, raw_details = details_tuple
    _print_section("=== placeDetails ===")
    _print_json(raw_details)


if __name__ == "__main__":
    main()
