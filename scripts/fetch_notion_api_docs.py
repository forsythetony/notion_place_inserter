#!/usr/bin/env python3
"""Fetch Notion API reference documentation from developers.notion.com."""

import argparse
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Reference API docs to fetch (from llms.txt)
REFERENCE_PAGES = [
    "authentication",
    "block",
    "capabilities",
    "changes-by-version",
    "comment-attachment",
    "comment-display-name",
    "comment-object",
    "complete-a-file-upload",
    "create-a-comment",
    "create-a-data-source",
    "create-a-database",
    "create-a-file-upload",
    "create-a-token",
    "data-source",
    "database",
    "database-create",
    "database-retrieve",
    "database-update",
    "delete-a-block",
    "emoji-object",
    "file-object",
    "file-upload",
    "filter-data-source-entries",
    "get-block-children",
    "get-databases",
    "get-self",
    "get-user",
    "get-users",
    "intro",
    "introspect-token",
    "list-comments",
    "list-data-source-templates",
    "list-file-uploads",
    "move-page",
    "page",
    "page-property-values",
    "parent-object",
    "patch-block-children",
    "patch-page",
    "post-database-query",
    "post-database-query-filter",
    "post-database-query-sort",
    "post-page",
    "post-search",
    "property-item-object",
    "property-object",
    "query-a-data-source",
    "refresh-a-token",
    "request-limits",
    "retrieve-a-block",
    "retrieve-a-data-source",
    "retrieve-a-database",
    "retrieve-a-file-upload",
    "retrieve-a-page",
    "retrieve-a-page-property",
    "retrieve-comment",
    "retrieve-page-markdown",
    "revoke-token",
    "rich-text",
    "search-optimizations-and-limitations",
    "send-a-file-upload",
    "sort-data-source-entries",
    "status-codes",
    "trash-page",
    "unfurl-attribute-object",
    "update-a-block",
    "update-a-data-source",
    "update-a-database",
    "update-data-source-properties",
    "update-page-markdown",
    "update-property-schema-object",
    "user",
    "versioning",
]


def fetch_url(url: str) -> str:
    """Fetch URL content with a polite User-Agent."""
    req = Request(url, headers={"User-Agent": "Notion-API-Docs-Fetcher/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_markdown_from_html(html: str) -> str:
    """Extract markdown-like content. The .md URLs may return raw markdown or HTML."""
    # Check if it's already markdown (starts with # or common markdown)
    if html.strip().startswith("#") or html.strip().startswith(">"):
        return html
    # If HTML, try to get the main content - for now return as-is and let user handle
    return html


def main():
    parser = argparse.ArgumentParser(description="Fetch Notion API docs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "resources" / "notion" / "api",
        help="Output directory for markdown files",
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests (seconds)")
    parser.add_argument("--skip-existing", action="store_true", help="Skip files that already exist")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_url = "https://developers.notion.com/reference"
    fetched = 0
    skipped = 0
    failed = []

    for page in REFERENCE_PAGES:
        out_path = args.output_dir / f"{page}.md"
        if args.skip_existing and out_path.exists():
            skipped += 1
            continue
        url = f"{base_url}/{page}.md"
        try:
            content = fetch_url(url)
            # Remove the "Content from URL" header if present
            if content.startswith("# Content from "):
                lines = content.split("\n")
                # Find first real heading (## or ###)
                start = 0
                for i, line in enumerate(lines):
                    if line.startswith("# ") and "Content from" not in line:
                        start = i
                        break
                    elif line.startswith("## ") or (line.startswith("# ") and i > 0):
                        start = i
                        break
                content = "\n".join(lines[start:])
            out_path.write_text(content, encoding="utf-8")
            fetched += 1
            print(f"Fetched: {page}.md")
        except (HTTPError, URLError) as e:
            failed.append((page, str(e)))
            print(f"Failed: {page} - {e}")
        time.sleep(args.delay)

    print(f"\nDone. Fetched: {fetched}, Skipped: {skipped}, Failed: {len(failed)}")
    if failed:
        for name, err in failed:
            print(f"  - {name}: {err}")


if __name__ == "__main__":
    main()
