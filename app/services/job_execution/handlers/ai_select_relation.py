"""AI Select Relation step runtime handler."""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.services.job_execution.runtime_types import ExecutionContext, StepExecutionHandle
from app.services.job_execution.step_runtime_base import StepRuntime
from app.services.pipeline_live_test.api_overrides import consume_manual_api_response


def _extract_title_from_rich_text(rich_text_array: list) -> str:
    """Extract plain text from Notion rich text array."""
    if not rich_text_array:
        return ""
    return "".join(
        block.get("plain_text", "") or block.get("text", {}).get("content", "")
        for block in rich_text_array
    )


def _extract_key_value_from_page(page: dict, key_lookup: str) -> str:
    """Extract lookup value from a Notion page by key. Supports title-type properties."""
    props = page.get("properties") or {}
    # Try exact match first
    if key_lookup in props:
        p = props[key_lookup]
        if p.get("type") == "title":
            return _extract_title_from_rich_text(p.get("title", []))
        if p.get("type") == "rich_text":
            return _extract_title_from_rich_text(p.get("rich_text", []))
        if p.get("type") == "select" and p.get("select"):
            return p["select"].get("name", "")
    # Try case-insensitive and common aliases
    key_lower = key_lookup.lower()
    for name, p in props.items():
        if name.lower() == key_lower and isinstance(p, dict):
            if p.get("type") == "title":
                return _extract_title_from_rich_text(p.get("title", []))
            if p.get("type") == "rich_text":
                return _extract_title_from_rich_text(p.get("rich_text", []))
            if p.get("type") == "select" and p.get("select"):
                return p["select"].get("name", "")
    # Fallback: first title property
    for p in props.values():
        if isinstance(p, dict) and p.get("type") == "title":
            return _extract_title_from_rich_text(p.get("title", []))
    return ""


def _resolve_filter_properties(notion_client, data_source_id: str, key_prop: str) -> list[str]:
    """
    Return a safe filter_properties list for data_sources.query.

    Notion rejects invalid attributes in filter_properties. We therefore only pass
    values that actually exist in the target data source schema.
    """
    aliases = [key_prop]
    if key_prop.lower() == "title":
        aliases.extend(["Name", "Title"])

    try:
        data_source = notion_client.data_sources.retrieve(data_source_id=data_source_id)
        raw_props = data_source.get("properties") or {}
    except Exception:
        return []

    if not isinstance(raw_props, dict) or not raw_props:
        return []

    valid: set[str] = set()
    valid_lower_to_canonical: dict[str, str] = {}
    for display_name, raw in raw_props.items():
        if isinstance(display_name, str) and display_name:
            valid.add(display_name)
            valid_lower_to_canonical[display_name.lower()] = display_name
        if isinstance(raw, dict):
            prop_id = raw.get("id")
            if isinstance(prop_id, str) and prop_id:
                valid.add(prop_id)
                valid_lower_to_canonical[prop_id.lower()] = prop_id

    resolved: list[str] = []
    for alias in aliases:
        if alias in valid and alias not in resolved:
            resolved.append(alias)
            continue
        canonical = valid_lower_to_canonical.get(alias.lower())
        if canonical and canonical not in resolved:
            resolved.append(canonical)
    return resolved


def _fetch_candidate_pages(notion_client, data_source_id: str, key_prop: str) -> list[dict]:
    """Query Notion data source for pages; return list of {id, key_value} dicts."""
    candidates: list[dict] = []
    start_cursor = None
    filter_props = _resolve_filter_properties(notion_client, data_source_id, key_prop)
    if not filter_props:
        logger.debug(
            "ai_select_relation_filter_props_unset | data_source_id={} key_prop={}",
            data_source_id,
            key_prop,
        )
    while True:
        try:
            body: dict = {"page_size": 100}
            if start_cursor:
                body["start_cursor"] = start_cursor
            if filter_props:
                resp = notion_client.data_sources.query(
                    data_source_id=data_source_id,
                    filter_properties=filter_props,
                    **body,
                )
            else:
                resp = notion_client.data_sources.query(
                    data_source_id=data_source_id,
                    **body,
                )
        except Exception as e:
            err_msg = str(e)
            invalid_filter = "filter_properties" in err_msg and "invalid attribute" in err_msg
            if invalid_filter and filter_props:
                logger.warning(
                    "ai_select_relation_invalid_filter_properties_retrying_unfiltered | data_source_id={} filter_props={} error={}",
                    data_source_id,
                    ",".join(filter_props),
                    err_msg,
                )
                filter_props = []
                continue
            hint = (
                " Ensure the Locations database is shared with your Notion integration."
                if "Could not find" in err_msg or "404" in err_msg or "not shared" in err_msg.lower()
                else ""
            )
            logger.error(
                "ai_select_relation_query_failed | data_source_id={} error={}{}",
                data_source_id,
                err_msg,
                hint,
            )
            return candidates
        results = resp.get("results") or []
        for page in results:
            if page.get("object") != "page":
                continue
            page_id = page.get("id")
            if not page_id:
                continue
            key_val = _extract_key_value_from_page(page, key_prop)
            candidates.append({"id": page_id, key_prop: key_val})
        has_more = resp.get("has_more", False)
        start_cursor = resp.get("next_cursor")
        if not has_more or not start_cursor:
            break
    return candidates


class AiSelectRelationHandler(StepRuntime):
    """Use AI to select the best relation from a related database by key lookup."""

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        input_bindings: dict[str, Any],
        resolved_inputs: dict[str, Any],
        ctx: ExecutionContext,
        step_handle: StepExecutionHandle,
        snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        source_value = resolved_inputs.get("source_value") or resolved_inputs.get("value")
        related_db = config.get("related_db")
        key_lookup = config.get("key_lookup") or "title"
        prompt = config.get("prompt")

        manual = consume_manual_api_response(ctx, "claude.ai_select_relation")
        if manual is not None and isinstance(manual, dict):
            step_handle.log_processing("Using live-test manual API override (claude.ai_select_relation).")
            return {
                "selected_page_pointer": manual.get("selected_page_pointer"),
                "selected_relation": manual.get("selected_relation") or [],
            }

        if not related_db:
            logger.warning("ai_select_relation_missing_related_db | step_id={}", step_id)
            return {"selected_page_pointer": None, "selected_relation": []}

        targets = snapshot.get("targets") or {}
        target_data = targets.get(related_db)
        if not target_data:
            target_data = snapshot.get("target") if related_db == snapshot.get("job", {}).get("target_id") else None
        if not target_data:
            logger.warning(
                "ai_select_relation_target_not_found | step_id={} related_db={}",
                step_id,
                related_db,
            )
            return {"selected_page_pointer": None, "selected_relation": []}

        notion = ctx.get_service("notion")
        if not notion or not hasattr(notion, "client"):
            logger.warning("ai_select_relation_no_notion | step_id={}", step_id)
            return {"selected_page_pointer": None, "selected_relation": []}

        data_source_id = None
        id_source = ""
        display_name = target_data.get("display_name", "")
        if notion and hasattr(notion, "get_data_source_id") and display_name:
            try:
                data_source_id = notion.get_data_source_id(display_name)
                id_source = "display_name"
            except (KeyError, Exception) as e:
                logger.debug(
                    "ai_select_relation_get_data_source_id_failed | display_name={} error={}",
                    display_name,
                    e,
                )
        if not data_source_id:
            data_source_id = target_data.get("external_target_id")
            id_source = "external_target_id" if data_source_id else ""
        if not data_source_id:
            logger.warning(
                "ai_select_relation_no_data_source | step_id={} related_db={} display_name={}",
                step_id,
                related_db,
                display_name,
            )
            return {"selected_page_pointer": None, "selected_relation": []}

        logger.debug(
            "ai_select_relation_resolved_id | step_id={} related_db={} id_source={}",
            step_id,
            related_db,
            id_source,
        )

        step_handle.log_processing(
            f"Querying Notion related data source for candidates (related_db={related_db!r}, key_lookup={key_lookup!r})."
        )
        candidates = _fetch_candidate_pages(notion.client, data_source_id, key_lookup)
        if not candidates:
            logger.info(
                "ai_select_relation_no_candidates | step_id={} related_db={}",
                step_id,
                related_db,
            )
            return {"selected_page_pointer": None, "selected_relation": []}

        source_context = source_value if isinstance(source_value, dict) else {"value": source_value}
        claude = ctx.get_service("claude")
        if not claude:
            logger.warning("ai_select_relation_no_claude | step_id={}", step_id)
            return {"selected_page_pointer": None, "selected_relation": []}

        step_handle.log_processing(
            f"Calling Claude to choose best relation (candidates_count={len(candidates)})."
        )
        selected_id = claude.choose_best_relation_from_candidates(
            source_context=source_context,
            candidates=candidates,
            key_lookup=key_lookup,
            prompt=prompt,
        )

        if not selected_id:
            return {"selected_page_pointer": None, "selected_relation": []}

        return {
            "selected_page_pointer": {"id": selected_id},
            "selected_relation": [{"id": selected_id}],
        }
