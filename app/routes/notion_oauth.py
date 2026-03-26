"""Notion OAuth and connection lifecycle routes."""

import os
from collections import defaultdict
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_managed_auth
from app.domain.targets import DataTarget, TargetSchemaSnapshot
from app.services.notion_oauth_service import (
    is_notion_oauth_configured,
    NotionOAuthService,
)

router = APIRouter(tags=["notion-oauth"])


def _get_oauth_service(request: Request) -> NotionOAuthService | None:
    return getattr(request.app.state, "notion_oauth_service", None)


def _frontend_base() -> str:
    return os.environ.get("FRONTEND_BASE_URL", "http://localhost:5173").rstrip("/")


class SelectDataSourcesRequest(BaseModel):
    """Request body for POST select data sources."""

    external_source_ids: list[str] = Field(..., min_length=1)


# Prefer these bootstrap targets when multiple data_targets share one Notion data_source_id.
_BOOTSTRAP_CANONICAL_ORDER = ("target_places_to_visit", "target_locations")


def _parse_iso_datetime(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def _source_row_refresh_time(row: dict[str, Any]) -> datetime | None:
    """Best timestamp for when this external source row was last refreshed in our DB."""
    seen = _parse_iso_datetime(row.get("last_seen_at"))
    updated = _parse_iso_datetime(row.get("updated_at"))
    if seen and updated:
        return max(seen, updated)
    return seen or updated


def _dedupe_external_sources_by_id(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per external_source_id; if duplicates exist, keep the most recently refreshed row."""
    merged: dict[str, dict[str, Any]] = {}
    for s in sources:
        eid = s.get("external_source_id") or ""
        if not eid:
            continue
        existing = merged.get(eid)
        if existing is None:
            merged[eid] = s
            continue
        t_new = _source_row_refresh_time(s)
        t_old = _source_row_refresh_time(existing)
        if t_new and (not t_old or t_new > t_old):
            merged[eid] = s
    return [merged[k] for k in sorted(merged.keys())]


def _pick_canonical_target_for_source(
    external_source_id: str, targets_for_eid: list[DataTarget]
) -> DataTarget | None:
    """
    Choose one data_target for schema/property display when several share external_target_id.
    Order: bootstrap ids first, then prefer a target with an active schema snapshot, then by id.
    """
    if not targets_for_eid:
        return None
    by_id = {t.id: t for t in targets_for_eid}
    for bid in _BOOTSTRAP_CANONICAL_ORDER:
        if bid in by_id:
            return by_id[bid]
    with_schema = [t for t in targets_for_eid if t.active_schema_snapshot_id]
    if with_schema:
        return sorted(with_schema, key=lambda t: t.id)[0]
    return sorted(targets_for_eid, key=lambda t: t.id)[0]


def _serialize_tracked_properties(snapshot: TargetSchemaSnapshot | None) -> list[dict[str, str]]:
    if not snapshot or not snapshot.properties:
        return []
    return [{"name": p.name, "property_type": p.property_type} for p in snapshot.properties]


async def _build_data_source_management_response(
    sources: list[dict[str, Any]],
    connector_instance_id: str,
    owner_user_id: str,
    target_repo: Any,
    target_schema_repo: Any,
) -> dict[str, Any]:
    """
    Shared payload for GET data-sources and POST refresh-sources: summary + enriched sources.
    Canonical Notion identity is external_source_id (data_source_id).
    """
    deduped = _dedupe_external_sources_by_id(sources)

    if not target_repo or not target_schema_repo:
        out: list[dict[str, Any]] = []
        for s in deduped:
            ts = _source_row_refresh_time(s)
            out.append({
                **s,
                "source_refreshed_at": ts.isoformat() if ts else None,
                "is_tracked": False,
                "last_properties_sync_at": None,
                "tracked_target_id": None,
                "tracked_properties": [],
            })
        return {"summary": _compute_source_summary(out), "sources": out}

    targets = await target_repo.list_by_connector(connector_instance_id, owner_user_id)
    by_external: dict[str, list[DataTarget]] = defaultdict(list)
    for t in targets:
        if t.external_target_id:
            by_external[t.external_target_id].append(t)

    snapshot_ids = [
        t.active_schema_snapshot_id for t in targets if t.active_schema_snapshot_id
    ]
    snapshot_fetched: dict[str, datetime] = (
        await target_schema_repo.get_fetched_at_for_snapshots(snapshot_ids, owner_user_id)
        if snapshot_ids
        else {}
    )

    schema_cache: dict[str, TargetSchemaSnapshot | None] = {}

    async def _get_snapshot(snap_id: str) -> TargetSchemaSnapshot | None:
        if snap_id not in schema_cache:
            schema_cache[snap_id] = await target_schema_repo.get_by_id(
                snap_id, owner_user_id
            )
        return schema_cache[snap_id]

    enriched: list[dict[str, Any]] = []
    for s in deduped:
        eid = s.get("external_source_id") or ""
        row_ts = _source_row_refresh_time(s)
        match = by_external.get(eid, [])
        is_tracked = len(match) > 0
        canonical = _pick_canonical_target_for_source(eid, match) if is_tracked else None

        last_sync: datetime | None = None
        tracked_props: list[dict[str, str]] = []
        tracked_tid: str | None = None
        if canonical:
            tracked_tid = canonical.id
            if canonical.active_schema_snapshot_id:
                last_sync = snapshot_fetched.get(canonical.active_schema_snapshot_id)
                snap = await _get_snapshot(canonical.active_schema_snapshot_id)
                tracked_props = _serialize_tracked_properties(snap)

        enriched.append({
            **s,
            "source_refreshed_at": row_ts.isoformat() if row_ts else None,
            "is_tracked": is_tracked,
            "last_properties_sync_at": last_sync.isoformat() if last_sync else None,
            "tracked_target_id": tracked_tid,
            "tracked_properties": tracked_props,
        })

    return {"summary": _compute_source_summary(enriched), "sources": enriched}


def _compute_source_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(sources)
    tracked = sum(1 for s in sources if s.get("is_tracked"))
    refresh_times: list[datetime] = []
    for s in sources:
        ts = _parse_iso_datetime(s.get("source_refreshed_at"))
        if ts:
            refresh_times.append(ts)
    last_ref = max(refresh_times) if refresh_times else None
    return {
        "totalSources": total,
        "trackedSources": tracked,
        "untrackedSources": max(0, total - tracked),
        "lastRefreshedAt": last_ref.isoformat() if last_ref else None,
    }


def _map_display_name_to_bootstrap_target(display_name: str) -> str | None:
    """
    Map a source display name to a bootstrap target ID.
    Returns target_places_to_visit, target_locations, or None if no match.
    """
    name = (display_name or "").strip().lower()
    if "locations" in name:
        return "target_locations"
    if "places" in name or "places to visit" in name:
        return "target_places_to_visit"
    return None


@router.post("/management/connections/notion/oauth/start")
async def start_notion_oauth(
    request: Request,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """
    Start Notion OAuth flow. Returns authorization_url for redirect.
    """
    if not is_notion_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Notion OAuth not configured (NOTION_OAUTH_CLIENT_ID, NOTION_OAUTH_CLIENT_SECRET, NOTION_OAUTH_REDIRECT_URI)",
        )
    svc = _get_oauth_service(request)
    if not svc:
        raise HTTPException(status_code=500, detail="OAuth service not available")
    success_redirect = f"{_frontend_base()}/connections?connected=notion"
    try:
        url = await svc.start_oauth(owner_user_id=ctx.user_id, success_redirect=success_redirect)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"authorization_url": url}


@router.get("/auth/callback/notion")
async def notion_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    """
    OAuth callback from Notion. Validates state, exchanges code, redirects to frontend.
    """
    if error:
        params = urlencode({"error": error})
        return RedirectResponse(url=f"{_frontend_base()}/connections?{params}", status_code=302)
    if not code or not state:
        return RedirectResponse(
            url=f"{_frontend_base()}/connections?error=missing_code_or_state",
            status_code=302,
        )
    svc = _get_oauth_service(request)
    if not svc:
        return RedirectResponse(
            url=f"{_frontend_base()}/connections?error=oauth_service_unavailable",
            status_code=302,
        )
    try:
        _, redirect_path = await svc.exchange_code_and_connect(code, state)
    except ValueError as e:
        err_param = urlencode({"error": str(e)})
        return RedirectResponse(
            url=f"{_frontend_base()}/connections?{err_param}",
            status_code=302,
        )
    return RedirectResponse(url=f"{_frontend_base()}{redirect_path}", status_code=302)


@router.post("/management/connections/{connection_id}/disconnect")
async def disconnect_connection(
    request: Request,
    connection_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """Disconnect a Notion connection. Revokes credentials and marks inactive."""
    if connection_id != "connector_instance_notion_default":
        raise HTTPException(status_code=404, detail="Connection not found")
    svc = _get_oauth_service(request)
    if not svc:
        raise HTTPException(status_code=500, detail="OAuth service not available")
    updated = await svc.disconnect(owner_user_id=ctx.user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "disconnected", "id": updated.id}


@router.post("/management/connections/{connection_id}/refresh-sources")
async def refresh_connection_sources(
    request: Request,
    connection_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """Refresh discovered Notion databases for a connection."""
    if connection_id != "connector_instance_notion_default":
        raise HTTPException(status_code=404, detail="Connection not found")
    svc = _get_oauth_service(request)
    if not svc:
        raise HTTPException(status_code=500, detail="OAuth service not available")
    ext_repo = getattr(request.app.state, "connector_external_sources_repository", None)
    if not ext_repo:
        raise HTTPException(status_code=500, detail="External sources repository not available")
    try:
        await svc.refresh_sources(owner_user_id=ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    sources = await ext_repo.list_for_instance(
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        provider="notion",
    )
    target_repo = getattr(request.app.state, "target_repository", None)
    target_schema_repo = getattr(request.app.state, "target_schema_repository", None)
    return await _build_data_source_management_response(
        sources,
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        target_repo=target_repo,
        target_schema_repo=target_schema_repo,
    )


@router.get("/management/connections/{connection_id}/data-sources")
async def list_connection_data_sources(
    request: Request,
    connection_id: str,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """List discovered Notion databases for a connection."""
    if connection_id != "connector_instance_notion_default":
        raise HTTPException(status_code=404, detail="Connection not found")
    ext_repo = getattr(request.app.state, "connector_external_sources_repository", None)
    if not ext_repo:
        raise HTTPException(status_code=500, detail="External sources repository not available")
    sources = await ext_repo.list_for_instance(
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        provider="notion",
    )
    target_repo = getattr(request.app.state, "target_repository", None)
    target_schema_repo = getattr(request.app.state, "target_schema_repository", None)
    return await _build_data_source_management_response(
        sources,
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        target_repo=target_repo,
        target_schema_repo=target_schema_repo,
    )


@router.post("/management/connections/{connection_id}/data-sources/select")
async def select_data_sources(
    request: Request,
    connection_id: str,
    body: SelectDataSourcesRequest,
    ctx: AuthContext = Depends(require_managed_auth),
):
    """Create data_targets for selected Notion databases."""
    if connection_id != "connector_instance_notion_default":
        raise HTTPException(status_code=404, detail="Connection not found")
    target_repo = getattr(request.app.state, "target_repository", None)
    ext_repo = getattr(request.app.state, "connector_external_sources_repository", None)
    schema_sync = getattr(request.app.state, "schema_sync_service", None)
    if not target_repo or not ext_repo:
        raise HTTPException(status_code=500, detail="Repository not available")
    sources = await ext_repo.list_for_instance(
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        provider="notion",
    )
    from app.domain.targets import DataTarget

    by_id = {s["external_source_id"]: s for s in sources}
    created = []
    # Map selected sources to bootstrap targets by display name; fallback by selection order.
    selection_for_places: tuple[str, str] | None = None  # (eid, display_name)
    selection_for_locations: tuple[str, str] | None = None
    selection_order: list[tuple[str, str]] = []  # [(eid, display_name), ...]

    for eid in body.external_source_ids:
        if eid not in by_id:
            continue
        s = by_id[eid]
        display_name = s.get("display_name", eid)
        selection_order.append((eid, display_name))

        target_id = f"target_notion_{eid.replace('-', '_')[:20]}"
        existing = await target_repo.get_by_id(target_id, ctx.user_id)
        if existing:
            created.append({"id": target_id, "display_name": display_name, "created": False})
            continue
        target = DataTarget(
            id=target_id,
            owner_user_id=ctx.user_id,
            target_template_id="notion_database",
            connector_instance_id="connector_instance_notion_default",
            display_name=display_name,
            external_target_id=eid,
            status="active",
            visibility="owner",
        )
        await target_repo.save(target)
        created.append({"id": target_id, "display_name": target.display_name, "created": True})
        if schema_sync:
            try:
                await schema_sync.sync_for_target(target_id, ctx.user_id)
            except Exception:
                pass

    # Map selections to bootstrap targets by display name, then by order.
    for eid, display_name in selection_order:
        mapped = _map_display_name_to_bootstrap_target(display_name)
        if mapped == "target_places_to_visit" and selection_for_places is None:
            selection_for_places = (eid, display_name)
        elif mapped == "target_locations" and selection_for_locations is None:
            selection_for_locations = (eid, display_name)
    if selection_for_places is None and selection_order:
        selection_for_places = selection_order[0]
    if selection_for_locations is None and len(selection_order) >= 2:
        selection_for_locations = selection_order[1]

    # Update bootstrap targets so job works after reconnect. Create target_locations if missing.
    for bootstrap_target_id, selection in [
        ("target_places_to_visit", selection_for_places),
        ("target_locations", selection_for_locations),
    ]:
        if not selection:
            continue
        eid, display_name = selection
        existing_bootstrap = await target_repo.get_by_id(bootstrap_target_id, ctx.user_id)
        if existing_bootstrap:
            updated = DataTarget(
                id=existing_bootstrap.id,
                owner_user_id=existing_bootstrap.owner_user_id,
                target_template_id=existing_bootstrap.target_template_id,
                connector_instance_id=existing_bootstrap.connector_instance_id,
                display_name=display_name or existing_bootstrap.display_name,
                external_target_id=eid,
                status="active",
                visibility=existing_bootstrap.visibility,
            )
            await target_repo.save(updated)
        else:
            # Create bootstrap target if missing (e.g. target_locations before bootstrap runs).
            updated = DataTarget(
                id=bootstrap_target_id,
                owner_user_id=ctx.user_id,
                target_template_id="notion_database",
                connector_instance_id="connector_instance_notion_default",
                display_name=display_name,
                external_target_id=eid,
                status="active",
                visibility="owner",
            )
            await target_repo.save(updated)
        if schema_sync:
            try:
                await schema_sync.sync_for_target(bootstrap_target_id, ctx.user_id)
            except Exception:
                pass
        created.append({"id": bootstrap_target_id, "display_name": updated.display_name, "created": existing_bootstrap is None})

    return {"targets": created}
