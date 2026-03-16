#!/usr/bin/env python3
"""
Test Notion database access via OAuth token.

Validates token validity by listing accessible data sources, pages, or by retrieving
a specific data source. Use to diagnose "Could not find data_source" errors
and verify integration sharing.
"""

import argparse
import csv
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
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
SEARCH_PAGE_SIZE = 100
OUTPUT_DIR = PROJECT_ROOT / "temp"
FETCH_TITLES_MAX_WORKERS = 10

CSV_FIELDS = [
    "type",
    "id",
    "display_name",
    "parent_type",
    "parent_id",
    "parent_database_name",
    "created_time",
    "last_edited_time",
    "url",
    "public_url",
    "in_trash",
    "database_parent_type",
    "database_parent_id",
]


def _extract_rich_text(blocks: list) -> str:
    """Extract plain text from Notion rich text / title array."""
    if not isinstance(blocks, list):
        return ""
    result = []
    for b in blocks:
        if isinstance(b, dict):
            text = b.get("plain_text") or (b.get("text") or {}).get("content", "")
            if text:
                result.append(text)
    return "".join(result)


def _extract_display_name(item: dict) -> str:
    """Extract display name from search result item (page or data_source)."""
    obj = item.get("object", "")

    # Data source: top-level name or title
    if obj in ("database", "data_source"):
        name = item.get("name") or ""
        if not name:
            name = _extract_rich_text(item.get("title") or [])
        if name:
            return name

    # Page: title is in properties (property name varies: Title, Name, title, etc.)
    props = item.get("properties") or {}
    for prop_name, prop_val in props.items():
        if not isinstance(prop_val, dict):
            continue
        if prop_val.get("type") == "title":
            title_arr = prop_val.get("title") or []
            name = _extract_rich_text(title_arr)
            if name:
                return name

    # Fallback: url slug (e.g. "Page-Name-abc123" -> "Page Name")
    url = item.get("url") or ""
    if url and "/" in url:
        slug = url.rstrip("/").split("/")[-1]
        if slug and len(slug) > 36:  # UUID is 36 chars; slug usually has name-hyphen-uuid
            name_part = slug.rsplit("-", 1)[0].replace("-", " ")
            if name_part:
                return name_part

    return item.get("id", "") or "Untitled"


def _extract_row_from_item(item: dict, kind: str) -> dict:
    """Extract CSV row from a page or data_source object (full or partial)."""
    item_id = item.get("id", "")
    display_name = _extract_display_name(item)
    parent = item.get("parent") or {}
    parent_type = parent.get("type", "")
    parent_id = (
        parent.get("page_id")
        or parent.get("data_source_id")
        or parent.get("database_id")
        or parent.get("block_id")
        or ""
    )
    db_parent = item.get("database_parent") or {}
    db_parent_type = db_parent.get("type", "")
    db_parent_id = (
        db_parent.get("page_id")
        or db_parent.get("database_id")
        or db_parent.get("data_source_id")
        or db_parent.get("block_id")
        or ""
    )
    return {
        "type": kind,
        "id": item_id,
        "display_name": display_name,
        "parent_type": parent_type,
        "parent_id": parent_id,
        "parent_database_name": "",  # Filled by _enrich_parent_database_names
        "created_time": item.get("created_time", ""),
        "last_edited_time": item.get("last_edited_time", ""),
        "url": item.get("url", ""),
        "public_url": item.get("public_url") or "",
        "in_trash": str(item.get("in_trash", "")).lower() if item.get("in_trash") is not None else "",
        "database_parent_type": db_parent_type,
        "database_parent_id": db_parent_id,
    }


def _fetch_parent_database_name(token: str, parent_id: str) -> tuple[str, str]:
    """Fetch display name for a database/data_source. Returns (parent_id, display_name)."""
    client = Client(auth=token)
    # Try data_sources first (used for data_source_id parent_type)
    try:
        ds = client.data_sources.retrieve(data_source_id=parent_id)
        return (parent_id, _extract_display_name(ds))
    except Exception:
        pass
    # Fallback to databases (used for database_id parent_type)
    try:
        db = client.databases.retrieve(database_id=parent_id)
        return (parent_id, _extract_display_name(db))
    except Exception:
        return (parent_id, "")


def _enrich_parent_database_names(token: str, rows: list[dict]) -> None:
    """Fetch parent database names and add parent_database_name to rows. Mutates rows in place."""
    to_fetch = set()
    for row in rows:
        pt = row.get("parent_type", "")
        pid = row.get("parent_id", "")
        if pid and pt in ("database_id", "data_source_id"):
            to_fetch.add(pid)

    if not to_fetch:
        return

    cache = {}
    with ThreadPoolExecutor(max_workers=FETCH_TITLES_MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_parent_database_name, token, pid): pid for pid in to_fetch}
        for future in as_completed(futures):
            pid, name = future.result()
            cache[pid] = name

    for row in rows:
        pid = row.get("parent_id", "")
        if pid and pid in cache:
            row["parent_database_name"] = cache[pid]


def _search_notion(
    token: str,
    *,
    object_filter: str | None = None,
    query: str | None = None,
    page_size: int = SEARCH_PAGE_SIZE,
) -> list[dict]:
    """Search Notion. object_filter: 'page', 'data_source', or None for both."""
    all_results = []
    cursor = None
    with httpx.Client() as client:
        while True:
            body = {"page_size": page_size}
            if object_filter:
                body["filter"] = {"property": "object", "value": object_filter}
            if query:
                body["query"] = query
            if cursor:
                body["start_cursor"] = cursor

            r = client.post(
                "https://api.notion.com/v1/search",
                json=body,
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
            all_results.extend(results)
            cursor = data.get("next_cursor")
            if not cursor or not data.get("has_more", False):
                break
    return all_results


def _fetch_full_item(token: str, item_id: str, kind: str) -> dict:
    """Fetch full object and extract full row for CSV. Returns row dict."""
    client = Client(auth=token)
    try:
        if kind == "data_source":
            full = client.data_sources.retrieve(data_source_id=item_id)
        else:
            full = client.pages.retrieve(page_id=item_id)
        return _extract_row_from_item(full, kind)
    except Exception:
        return _extract_row_from_item({"id": item_id, "object": kind}, kind)


def list_data_sources(
    token: str, query: str | None = None, fetch_titles: bool = False
) -> list[dict]:
    """List data sources accessible with the given OAuth token."""
    results = _search_notion(token, object_filter="data_source", query=query)
    items = []
    to_fetch = []
    for item in results:
        obj = item.get("object")
        if obj not in ("database", "data_source"):
            continue
        ds_id = item.get("id")
        if not ds_id:
            continue
        row = _extract_row_from_item(item, "data_source")
        if fetch_titles and (row["display_name"] == ds_id or row["display_name"] == "Untitled"):
            to_fetch.append((ds_id, "data_source"))
        else:
            items.append(row)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=FETCH_TITLES_MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_full_item, token, iid, kind): iid
                for iid, kind in to_fetch
            }
            for future in as_completed(futures):
                row = future.result()
                items.append(row)
        # Preserve original search order
        order = {r["id"]: i for i, r in enumerate(results) if r.get("id")}
        items.sort(key=lambda x: order.get(x["id"], 999))

    return items


def list_pages(
    token: str, query: str | None = None, fetch_titles: bool = False
) -> list[dict]:
    """List pages accessible with the given OAuth token."""
    results = _search_notion(token, object_filter="page", query=query)
    items = []
    to_fetch = []
    for item in results:
        if item.get("object") != "page":
            continue
        page_id = item.get("id")
        if not page_id:
            continue
        row = _extract_row_from_item(item, "page")
        if fetch_titles and (row["display_name"] == page_id or row["display_name"] == "Untitled"):
            to_fetch.append((page_id, "page"))
        else:
            items.append(row)

    if to_fetch:
        with ThreadPoolExecutor(max_workers=FETCH_TITLES_MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_full_item, token, iid, kind): iid
                for iid, kind in to_fetch
            }
            for future in as_completed(futures):
                row = future.result()
                items.append(row)
        # Preserve original search order
        order = {r["id"]: i for i, r in enumerate(results) if r.get("id")}
        items.sort(key=lambda x: order.get(x["id"], 999))

    return items


def retrieve_data_source(token: str, data_source_id: str) -> dict:
    """Retrieve a specific data source or database by ID.

    Notion search with object filter "data_source" can still return "database"
    objects/IDs in some workspaces. To keep this diagnostic script practical,
    we try the data source endpoint first, then fall back to database retrieve.
    """
    client = Client(auth=token)
    try:
        return client.data_sources.retrieve(data_source_id=data_source_id)
    except APIResponseError as e_data_source:
        try:
            return client.databases.retrieve(database_id=data_source_id)
        except APIResponseError:
            raise e_data_source


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test Notion database access via OAuth token. Lists accessible data sources, pages, or checks a specific data source."
    )
    parser.add_argument(
        "--token",
        type=str,
        help="OAuth access token (default: NOTION_OAUTH_TEST_TOKEN from env)",
    )
    parser.add_argument(
        "--data-source-id",
        type=str,
        help="Optional: data source or database ID to test (e.g. from error logs or Connections UI)",
    )
    parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only list accessible data sources; do not test a specific ID",
    )
    parser.add_argument(
        "--list-pages",
        action="store_true",
        help="List accessible pages (instead of data sources)",
    )
    parser.add_argument(
        "--list-all",
        action="store_true",
        help="List both data sources and pages",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Search query: filter results by title (works with --list-only, --list-pages, --list-all)",
    )
    parser.add_argument(
        "--output-csv",
        action="store_true",
        help="Save results to CSV in temp/ (gitignored)",
    )
    parser.add_argument(
        "--fetch-titles",
        action="store_true",
        help="Fetch full objects when search returns partial (slower, more API calls)",
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
        if args.data_source_id and not args.list_only and not args.list_pages and not args.list_all:
            logger.info("Testing access to data_source_id={}", args.data_source_id)
            ds = retrieve_data_source(token, args.data_source_id)
            name = _extract_display_name(ds) if isinstance(ds, dict) else ""
            obj = ds.get("object", "") if isinstance(ds, dict) else ""
            logger.info(
                "SUCCESS | data_source_id={} object={} display_name={}",
                args.data_source_id,
                obj,
                name,
            )
            if args.verbose:
                ic(ds)
            return 0

        query = args.query.strip() if args.query else None
        if query:
            logger.info("Search query: {!r}", query)

        all_rows = []

        if args.list_pages or args.list_all:
            logger.info("Listing accessible pages...")
            pages = list_pages(token, query=query, fetch_titles=args.fetch_titles)
            if not pages:
                logger.warning("No pages found.")
            else:
                logger.info("Found {} accessible page(s):", len(pages))
                for p in pages:
                    logger.info("  id={} display_name={}", p["id"], p["display_name"])
                    all_rows.append(p)

        if args.list_only or args.list_all or (not args.list_pages and not args.list_all):
            if args.list_all:
                logger.info("")
            logger.info("Listing accessible data sources...")
            sources = list_data_sources(token, query=query, fetch_titles=args.fetch_titles)
            if not sources:
                logger.warning("No data sources found. Ensure databases are shared with your integration.")
            else:
                logger.info("Found {} accessible data source(s):", len(sources))
                for s in sources:
                    logger.info("  id={} display_name={}", s["id"], s["display_name"])
                    all_rows.append(s)

        if all_rows:
            _enrich_parent_database_names(token, all_rows)

        if args.output_csv and all_rows:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            csv_path = OUTPUT_DIR / f"notion_oauth_export_{timestamp}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(all_rows)
            logger.info("Saved {} row(s) to {}", len(all_rows), csv_path)

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
