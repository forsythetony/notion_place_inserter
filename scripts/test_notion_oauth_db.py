#!/usr/bin/env python3
"""
Test Notion database access via OAuth token.

Validates token validity by listing accessible data sources or by retrieving
a specific data source. Use to diagnose "Could not find data_source" errors
and verify integration sharing.
"""

import argparse
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
from icecream import ic
from loguru import logger
from notion_client import Client
from notion_client.errors import APIResponseError

NOTION_API_VERSION = "2022-06-28"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / "envs" / "local.env"


def _extract_display_name(item: dict) -> str:
    """Extract display name from search result item."""
    name = item.get("name") or ""
    if not name:
        title_arr = item.get("title") or []
        if isinstance(title_arr, list):
            for b in title_arr:
                if isinstance(b, dict):
                    name += b.get("plain_text", "") or b.get("text", {}).get("content", "")
    return name or item.get("id", "") or "Untitled"


def list_data_sources(token: str) -> list[dict]:
    """List data sources accessible with the given OAuth token."""
    with httpx.Client() as client:
        r = client.post(
            "https://api.notion.com/v1/search",
            json={"filter": {"property": "object", "value": "data_source"}},
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": NOTION_API_VERSION,
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    if r.status_code != 200:
        err = r.json() if "application/json" in (r.headers.get("content-type") or "") else {}
        msg = err.get("message", r.text) or f"Search failed: {r.status_code}"
        raise ValueError(msg)

    data = r.json()
    results = data.get("results") or []
    sources = []
    for item in results:
        obj = item.get("object")
        if obj not in ("database", "data_source"):
            continue
        ds_id = item.get("id")
        if not ds_id:
            continue
        sources.append({
            "id": ds_id,
            "display_name": _extract_display_name(item),
        })
    return sources


def retrieve_data_source(token: str, data_source_id: str) -> dict:
    """Retrieve a specific data source by ID. Raises APIResponseError on failure."""
    client = Client(auth=token)
    return client.data_sources.retrieve(data_source_id=data_source_id)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test Notion database access via OAuth token. Lists accessible data sources or checks a specific one."
    )
    parser.add_argument(
        "--token",
        type=str,
        help="OAuth access token (default: NOTION_OAUTH_TEST_TOKEN from env)",
    )
    parser.add_argument(
        "--data-source-id",
        type=str,
        help="Optional: data source ID to test (e.g. from error logs or Connections UI)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list accessible data sources; do not test a specific ID",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    token = args.token or os.environ.get("NOTION_OAUTH_TEST_TOKEN", "").strip()
    if not token:
        logger.error(
            "No token provided. Set NOTION_OAUTH_TEST_TOKEN in envs/local.env or pass --token"
        )
        return 1

    if args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")

    try:
        if args.data_source_id and not args.list_only:
            logger.info("Testing access to data_source_id={}", args.data_source_id)
            ds = retrieve_data_source(token, args.data_source_id)
            name = _extract_display_name(ds) if isinstance(ds, dict) else ""
            logger.info(
                "SUCCESS | data_source_id={} display_name={}",
                args.data_source_id,
                name,
            )
            if args.verbose:
                ic(ds)
            return 0

        logger.info("Listing accessible data sources...")
        sources = list_data_sources(token)
        if not sources:
            logger.warning("No data sources found. Ensure databases are shared with your integration.")
            return 0

        logger.info("Found {} accessible data source(s):", len(sources))
        for s in sources:
            logger.info("  id={} display_name={}", s["id"], s["display_name"])
        return 0

    except APIResponseError as e:
        code = getattr(e, "code", "")
        status = getattr(e, "status", "")
        msg = str(e)
        logger.error(
            "Notion API error | code={} status={} message={}",
            code,
            status,
            msg[:400],
        )
        if "Could not find data_source" in msg or "object_not_found" in str(code).lower():
            logger.info(
                "Hint: Share the database with your integration (Place Inserter) in Notion: "
                "open the database → Share → invite your integration"
            )
        return 1
    except ValueError as e:
        logger.error("Error: {}", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
