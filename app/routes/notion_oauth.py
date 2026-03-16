"""Notion OAuth and connection lifecycle routes."""

import os
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, require_managed_auth
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


@router.post("/management/connections/notion/oauth/start")
def start_notion_oauth(
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
        url = svc.start_oauth(owner_user_id=ctx.user_id, success_redirect=success_redirect)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"authorization_url": url}


@router.get("/auth/callback/notion")
def notion_oauth_callback(
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
        _, redirect_path = svc.exchange_code_and_connect(code, state)
    except ValueError as e:
        err_param = urlencode({"error": str(e)})
        return RedirectResponse(
            url=f"{_frontend_base()}/connections?{err_param}",
            status_code=302,
        )
    return RedirectResponse(url=f"{_frontend_base()}{redirect_path}", status_code=302)


@router.post("/management/connections/{connection_id}/disconnect")
def disconnect_connection(
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
    updated = svc.disconnect(owner_user_id=ctx.user_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"status": "disconnected", "id": updated.id}


@router.post("/management/connections/{connection_id}/refresh-sources")
def refresh_connection_sources(
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
    try:
        sources = svc.refresh_sources(owner_user_id=ctx.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"sources": sources}


@router.get("/management/connections/{connection_id}/data-sources")
def list_connection_data_sources(
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
    sources = ext_repo.list_for_instance(
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        provider="notion",
    )
    return {"sources": sources}


@router.post("/management/connections/{connection_id}/data-sources/select")
def select_data_sources(
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
    sources = ext_repo.list_for_instance(
        connector_instance_id="connector_instance_notion_default",
        owner_user_id=ctx.user_id,
        provider="notion",
    )
    by_id = {s["external_source_id"]: s for s in sources}
    created = []
    first_selected_display_name = None
    first_selected_eid = None
    for eid in body.external_source_ids:
        if eid not in by_id:
            continue
        s = by_id[eid]
        if first_selected_eid is None:
            first_selected_eid = eid
            first_selected_display_name = s.get("display_name", eid)
        target_id = f"target_notion_{eid.replace('-', '_')[:20]}"
        from app.domain.targets import DataTarget

        existing = target_repo.get_by_id(target_id, ctx.user_id)
        if existing:
            created.append({"id": target_id, "display_name": s.get("display_name", eid), "created": False})
            continue
        target = DataTarget(
            id=target_id,
            owner_user_id=ctx.user_id,
            target_template_id="notion_database",
            connector_instance_id="connector_instance_notion_default",
            display_name=s.get("display_name", eid),
            external_target_id=eid,
            status="active",
            visibility="owner",
        )
        target_repo.save(target)
        created.append({"id": target_id, "display_name": target.display_name, "created": True})
        if schema_sync:
            try:
                schema_sync.sync_for_target(target_id, ctx.user_id)
            except Exception:
                pass

    # Update bootstrap target (target_places_to_visit) with first selected so job works after
    # reconnect. Enables reset-and-reconnect flow without manual job reconfiguration.
    bootstrap_target_id = "target_places_to_visit"
    if first_selected_eid:
        existing_bootstrap = target_repo.get_by_id(bootstrap_target_id, ctx.user_id)
        if existing_bootstrap:
            from app.domain.targets import DataTarget

            updated = DataTarget(
                id=existing_bootstrap.id,
                owner_user_id=existing_bootstrap.owner_user_id,
                target_template_id=existing_bootstrap.target_template_id,
                connector_instance_id=existing_bootstrap.connector_instance_id,
                display_name=first_selected_display_name or existing_bootstrap.display_name,
                external_target_id=first_selected_eid,
                status="active",
                visibility=existing_bootstrap.visibility,
            )
            target_repo.save(updated)
            if schema_sync:
                try:
                    schema_sync.sync_for_target(bootstrap_target_id, ctx.user_id)
                except Exception:
                    pass
            created.append({"id": bootstrap_target_id, "display_name": updated.display_name, "created": False})

    return {"targets": created}
