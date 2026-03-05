#!/usr/bin/env python3
"""Pull Notion page or database data from a clipboard link and store in output folder."""

import argparse
import json
import re
from pathlib import Path

from dotenv import load_dotenv
from icecream import ic
from loguru import logger
from notion_client import Client
from notion_client.errors import APIResponseError

# Resolve paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = PROJECT_ROOT / "envs" / "local.env"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def extract_id(url_or_id: str) -> str | None:
    """Extract Notion page/database ID from URL or return as-is if already an ID."""
    url_or_id = url_or_id.strip()
    # Match UUID with optional hyphens (32 hex chars)
    uuid_pattern = re.compile(
        r"([0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12})",
        re.IGNORECASE,
    )
    # Try to find ID in notion.so URL
    if "notion.so" in url_or_id or "notion.site" in url_or_id:
        match = uuid_pattern.search(url_or_id)
        if match:
            page_id = match.group(1).replace("-", "")
            # Format as UUID for API (add hyphens)
            return f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
    # Assume it's already a page ID
    if uuid_pattern.fullmatch(url_or_id.replace("-", "")):
        pid = url_or_id.replace("-", "")
        return f"{pid[:8]}-{pid[8:12]}-{pid[12:16]}-{pid[16:20]}-{pid[20:]}"
    return None


def fetch_block_children(client: Client, block_id: str) -> list[dict]:
    """Recursively fetch all block children."""
    blocks = []
    has_more = True
    start_cursor = None

    while has_more:
        resp = client.blocks.children.list(
            block_id=block_id,
            start_cursor=start_cursor,
            page_size=100,
        )
        blocks.extend(resp.get("results", []))
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")

    # Recursively fetch children of blocks that have them
    for block in blocks:
        if block.get("has_children"):
            block_id_inner = block["id"]
            block["children"] = fetch_block_children(client, block_id_inner)
        else:
            block["children"] = []

    return blocks


def main():
    parser = argparse.ArgumentParser(
        description="Pull Notion page or database data from clipboard link and store in output folder"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Notion page URL or ID (default: read from clipboard)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory for page data",
    )
    parser.add_argument(
        "--format",
        choices=["json"],
        default="json",
        help="Output format",
    )
    args = parser.parse_args()

    load_dotenv(ENV_PATH)
    api_key = __import__("os").environ.get("NOTION_API_KEY")
    if not api_key:
        logger.error("NOTION_API_KEY not set in envs/local.env")
        raise SystemExit(1)

    url_or_id = args.url
    if not url_or_id:
        try:
            import pyperclip

            url_or_id = pyperclip.paste()
        except ImportError:
            logger.error("Install pyperclip for clipboard support, or pass --url")
            raise SystemExit(1)

    obj_id = extract_id(url_or_id)
    if not obj_id:
        logger.error("Could not extract page/database ID from: {}", url_or_id[:80])
        raise SystemExit(1)

    ic(obj_id)

    client = Client(auth=api_key)

    # Try page first; if it's a database, use database APIs
    try:
        logger.info("Fetching page {}", obj_id)
        page = client.pages.retrieve(page_id=obj_id)
        logger.info("Fetching block children...")
        blocks = fetch_block_children(client, obj_id)
        output = {"type": "page", "page": page, "blocks": blocks}
    except APIResponseError as e:
        err_msg = str(e).lower()
        if "database" in err_msg and "not a page" in err_msg:
            logger.info("Detected database, fetching structure (properties)...")
            database = client.databases.retrieve(database_id=obj_id)
            data_sources = database.get("data_sources", [])
            schemas = []
            for ds in data_sources:
                ds_id = ds.get("id")
                if ds_id:
                    ds_full = client.data_sources.retrieve(data_source_id=ds_id)
                    schemas.append(
                        {
                            "name": ds.get("name"),
                            "id": ds_id,
                            "properties": ds_full.get("properties", {}),
                        }
                    )
            output = {
                "type": "database",
                "database": database,
                "data_source_schemas": schemas,
            }
        else:
            code = str(getattr(e, "code", ""))
            if "object_not_found" in code or "404" in str(e):
                logger.error(
                    "Not found. Share the page/database with your Notion integration: "
                    "open it → Share → invite your integration"
                )
            raise

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.output_dir / f"{obj_id.replace('-', '')}.json"
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    logger.info("Saved to {}", out_path)


if __name__ == "__main__":
    main()
