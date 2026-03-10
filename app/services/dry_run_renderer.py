"""Render dry-run property previews as a rich table for local debugging."""

from rich.console import Console
from rich.table import Table
from rich.text import Text


def _extract_property_preview(prop_value: dict) -> str | Text:
    """Extract a compact human-readable preview from a Notion API property value."""
    if not prop_value:
        return ""

    if "title" in prop_value:
        blocks = prop_value["title"] or []
        return "".join(
            b.get("plain_text", "") or b.get("text", {}).get("content", "")
            for b in blocks
        )

    if "rich_text" in prop_value:
        blocks = prop_value["rich_text"] or []
        text = "".join(
            b.get("plain_text", "") or b.get("text", {}).get("content", "")
            for b in blocks
        )
        return text[:80] + ("..." if len(text) > 80 else "")

    if "url" in prop_value:
        return prop_value["url"] or ""

    if "select" in prop_value:
        sel = prop_value["select"]
        return sel.get("name", "") if sel else ""

    if "multi_select" in prop_value:
        items = prop_value["multi_select"] or []
        return ", ".join(i.get("name", "") for i in items)

    if "checkbox" in prop_value:
        return str(prop_value["checkbox"])

    if "number" in prop_value:
        val = prop_value["number"]
        return str(val) if val is not None else ""

    if "date" in prop_value:
        d = prop_value["date"]
        if not d:
            return ""
        start = d.get("start", "")
        end = d.get("end", "")
        return f"{start} → {end}" if end else start

    if "email" in prop_value:
        return prop_value["email"] or ""

    if "phone_number" in prop_value:
        return prop_value["phone_number"] or ""

    if "relation" in prop_value:
        rel_list = prop_value.get("relation") or []
        if not rel_list:
            return "—"
        parts: list[Text | str] = []
        for i, item in enumerate(rel_list):
            page_id = item.get("id") if isinstance(item, dict) else None
            if not page_id:
                continue
            # Notion URLs use page ID without hyphens (e.g. notion.so/544d579793444258aed61f72e66b6927)
            page_id_compact = str(page_id).replace("-", "")
            url = f"https://www.notion.so/{page_id_compact}"
            parts.append(Text(url, style=f"link {url}"))
            if i < len(rel_list) - 1:
                parts.append(" | ")
        if not parts:
            return "—"
        return Text.assemble(*parts)

    return str(prop_value)[:60]


def _get_property_type(prop_value: dict) -> str:
    """Return the Notion property type key from a property value."""
    for key in ("title", "rich_text", "url", "select", "multi_select", "checkbox", "number", "date", "email", "phone_number", "relation"):
        if key in prop_value:
            return key
    return "?"


def _extract_icon_preview(icon: dict | None) -> str | Text:
    """Extract a compact preview for page icon (emoji or external)."""
    if not icon:
        return ""
    if icon.get("type") == "emoji" and "emoji" in icon:
        return icon["emoji"]
    if icon.get("type") == "external" and "external" in icon:
        url = icon["external"].get("url", "")
        if not url:
            return ""
        if len(url) > 80:
            url = url[:80] + "..."
        return Text(url, style=f"link {icon['external'].get('url', '')}")
    return str(icon)[:60]


def _extract_cover_preview(cover: dict | None) -> str | Text:
    """Extract a compact preview for page cover (external URL or file_upload)."""
    if not cover:
        return ""
    if cover.get("type") == "external" and "external" in cover:
        url = cover["external"].get("url", "")
        if len(url) > 80:
            return url[:80] + "..."
        return Text(url, style=f"link {url}") if url else ""
    if cover.get("type") == "file_upload" and "file_upload" in cover:
        upload_id = cover["file_upload"].get("id", "")
        return f"(uploaded: {upload_id[:8]}...)" if upload_id else "(uploaded)"
    return str(cover)[:60]


def render_dry_run_table(
    database: str,
    properties: dict,
    keywords: str | None = None,
    *,
    property_sources: dict[str, str] | None = None,
    property_skips: dict[str, str] | None = None,
    property_omissions: dict[str, dict[str, str]] | None = None,
    icon: dict | None = None,
    cover: dict | None = None,
    console: Console | None = None,
) -> None:
    """
    Print a rich table of resolved Notion properties for dry-run debugging.
    Includes rows for intentionally skipped properties (NoOp) and page-level icon/cover when present.
    Does not modify the returned API response.
    """
    con = console or Console()
    table = Table(title=f"Dry Run: {database}")
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Value", style="green")
    table.add_column("Resolved By", style="dim")

    if keywords:
        table.caption = f"Keywords: {keywords}"

    sources = property_sources or {}
    skips = property_skips or {}
    omissions = property_omissions or {}

    for prop_name, prop_value in properties.items():
        prop_type = _get_property_type(prop_value)
        preview = _extract_property_preview(prop_value)
        resolved_by = sources.get(prop_name, "—")
        table.add_row(prop_name, prop_type, preview, resolved_by)

    # Page-level icon and cover (not database properties)
    if icon is not None:
        preview = _extract_icon_preview(icon)
        table.add_row("Icon", "emoji" if icon.get("type") == "emoji" else "external", preview, "resolve_icon_emoji")
    else:
        table.add_row("Icon", "—", "(skipped)", "—")

    if cover is not None:
        preview = _extract_cover_preview(cover)
        cover_type = cover.get("type", "external") if isinstance(cover, dict) else "external"
        table.add_row("Cover", cover_type, preview, "resolve_cover_image")
    else:
        table.add_row("Cover", "—", "(skipped)", "—")

    for prop_name, pipeline_id in skips.items():
        if prop_name not in properties:
            table.add_row(prop_name, "—", "(skipped)", pipeline_id)

    for prop_name, omission in omissions.items():
        if prop_name in properties or prop_name in skips:
            continue
        pipeline_id = omission.get("pipeline_id", "—")
        reason = omission.get("reason", "no_value")
        value = "(no value)" if reason == "no_value" else f"(no value: {reason})"
        table.add_row(prop_name, "—", value, pipeline_id)

    con.print(table)
