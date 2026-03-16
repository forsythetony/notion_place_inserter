"""Notion OAuth flow and connection lifecycle service."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx
from loguru import logger

from app.domain.connectors import ConnectorInstance


NOTION_OAUTH_AUTHORIZE = "https://api.notion.com/v1/oauth/authorize"
NOTION_OAUTH_TOKEN = "https://api.notion.com/v1/oauth/token"
NOTION_API_VERSION = "2022-06-28"  # OAuth endpoints support this version

NOTION_CONNECTOR_TEMPLATE_ID = "notion_oauth_workspace"
NOTION_CONNECTOR_INSTANCE_ID = "connector_instance_notion_default"


def _state_hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _get_oauth_config() -> tuple[str, str, str]:
    client_id = os.environ.get("NOTION_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NOTION_OAUTH_CLIENT_SECRET", "").strip()
    redirect_uri = os.environ.get("NOTION_OAUTH_REDIRECT_URI", "").strip()
    return client_id, client_secret, redirect_uri


def is_notion_oauth_configured() -> bool:
    """Return True if OAuth env vars are set."""
    client_id, client_secret, redirect_uri = _get_oauth_config()
    return bool(client_id and client_secret and redirect_uri)


class NotionOAuthService:
    """Handles Notion OAuth start, callback, token exchange, and source discovery."""

    def __init__(
        self,
        oauth_state_repo: Any,
        credentials_repo: Any,
        external_sources_repo: Any,
        connector_instance_repo: Any,
    ) -> None:
        self._oauth_state = oauth_state_repo
        self._credentials = credentials_repo
        self._external_sources = external_sources_repo
        self._connector_instances = connector_instance_repo

    def start_oauth(self, owner_user_id: str, success_redirect: str) -> str:
        """
        Create OAuth state, return authorization URL for Notion.
        success_redirect: where to send user after callback (e.g. /connections?connected=notion).
        """
        client_id, _, redirect_uri = _get_oauth_config()
        if not client_id or not redirect_uri:
            raise ValueError("NOTION_OAUTH_CLIENT_ID and NOTION_OAUTH_REDIRECT_URI required")

        state = secrets.token_urlsafe(32)
        state_hash = _state_hash(state)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        self._oauth_state.create(
            owner_user_id=owner_user_id,
            provider="notion",
            state_token_hash=state_hash,
            redirect_uri=redirect_uri,
            expires_at=expires_at,
        )
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "owner": "user",
            "state": state,
        }
        url = f"{NOTION_OAUTH_AUTHORIZE}?{urlencode(params)}"
        return url

    def exchange_code_and_connect(self, code: str, state: str) -> tuple[ConnectorInstance, str]:
        """
        Validate state, exchange code for tokens, upsert connector + credentials.
        Returns (connector_instance, success_redirect_path).
        """
        state_hash = _state_hash(state)
        state_row = self._oauth_state.consume_by_state_hash(state_hash)
        if not state_row:
            raise ValueError("Invalid or expired state")
        owner_user_id = str(state_row.get("owner_user_id", ""))
        if not owner_user_id:
            raise ValueError("State missing owner_user_id")

        client_id, client_secret, redirect_uri = _get_oauth_config()
        if not all([client_id, client_secret, redirect_uri]):
            raise ValueError("OAuth not configured")

        auth = (client_id, client_secret)
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        with httpx.Client() as client:
            r = client.post(
                NOTION_OAUTH_TOKEN,
                json=body,
                auth=auth,
                headers={
                    "Notion-Version": NOTION_API_VERSION,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
        if r.status_code != 200:
            err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            msg = err.get("message", r.text) or f"Token exchange failed: {r.status_code}"
            logger.warning("notion_oauth_token_exchange_failed | status={} error={}", r.status_code, msg)
            raise ValueError(msg)

        data = r.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        workspace_id = data.get("workspace_id", "")
        workspace_name = data.get("workspace_name", "") or "Notion workspace"
        if not access_token:
            raise ValueError("No access_token in response")

        token_payload = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "workspace_id": workspace_id,
            "workspace_name": workspace_name,
        }
        secret_ref = f"notion_oauth:{owner_user_id}:{NOTION_CONNECTOR_INSTANCE_ID}"
        self._credentials.upsert(
            connector_instance_id=NOTION_CONNECTOR_INSTANCE_ID,
            owner_user_id=owner_user_id,
            provider="notion",
            secret_ref=secret_ref,
            token_payload=token_payload,
        )

        existing = self._connector_instances.get_by_id(NOTION_CONNECTOR_INSTANCE_ID, owner_user_id)
        now = datetime.now(timezone.utc)
        if existing:
            updated = ConnectorInstance(
                id=existing.id,
                owner_user_id=existing.owner_user_id,
                connector_template_id=existing.connector_template_id,
                display_name=existing.display_name,
                status="active",
                config=existing.config,
                secret_ref=secret_ref,
                visibility=existing.visibility,
                last_validated_at=existing.last_validated_at,
                last_error=None,
                auth_status="connected",
                authorized_at=now,
                disconnected_at=None,
                provider_account_id=workspace_id,
                provider_account_name=workspace_name,
                last_synced_at=now,
                metadata=existing.metadata or {},
            )
        else:
            updated = ConnectorInstance(
                id=NOTION_CONNECTOR_INSTANCE_ID,
                owner_user_id=owner_user_id,
                connector_template_id=NOTION_CONNECTOR_TEMPLATE_ID,
                display_name="Notion",
                status="active",
                config={},
                secret_ref=secret_ref,
                visibility="owner",
                last_validated_at=None,
                last_error=None,
                auth_status="connected",
                authorized_at=now,
                disconnected_at=None,
                provider_account_id=workspace_id,
                provider_account_name=workspace_name,
                last_synced_at=now,
                metadata={},
            )
        self._connector_instances.save(updated)
        logger.info(
            "notion_oauth_connected | owner={} workspace={}",
            owner_user_id,
            workspace_name,
        )
        return updated, "/connections?connected=notion"

    def disconnect(self, owner_user_id: str) -> ConnectorInstance | None:
        """Mark connection disconnected, revoke credentials."""
        inst = self._connector_instances.get_by_id(NOTION_CONNECTOR_INSTANCE_ID, owner_user_id)
        if not inst:
            return None
        self._credentials.revoke(
            connector_instance_id=NOTION_CONNECTOR_INSTANCE_ID,
            owner_user_id=owner_user_id,
            provider="notion",
        )
        now = datetime.now(timezone.utc)
        updated = ConnectorInstance(
            id=inst.id,
            owner_user_id=inst.owner_user_id,
            connector_template_id=inst.connector_template_id,
            display_name=inst.display_name,
            status="inactive",
            config=inst.config,
            secret_ref=None,
            visibility=inst.visibility,
            last_validated_at=inst.last_validated_at,
            last_error=inst.last_error,
            auth_status="revoked",
            authorized_at=inst.authorized_at,
            disconnected_at=now,
            provider_account_id=inst.provider_account_id,
            provider_account_name=inst.provider_account_name,
            last_synced_at=inst.last_synced_at,
            metadata=inst.metadata or {},
        )
        self._connector_instances.save(updated)
        logger.info("notion_oauth_disconnected | owner={}", owner_user_id)
        return updated

    def get_access_token(self, owner_user_id: str) -> str | None:
        """Return access token for the owner's Notion connection, or None."""
        cred = self._credentials.get_for_instance(
            NOTION_CONNECTOR_INSTANCE_ID, owner_user_id, "notion"
        )
        if not cred:
            return None
        payload = cred.get("token_payload") or {}
        return payload.get("access_token")

    def refresh_sources(self, owner_user_id: str) -> list[dict[str, Any]]:
        """
        Call Notion search to discover databases, upsert into connector_external_sources.
        Returns list of {external_source_id, display_name, is_accessible}.
        """
        token = self.get_access_token(owner_user_id)
        if not token:
            raise ValueError("Not connected to Notion")

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
            db_id = item.get("id")
            if not db_id:
                continue
            name = item.get("name") or ""
            if not name:
                title_arr = item.get("title") or []
                if isinstance(title_arr, list):
                    for b in title_arr:
                        if isinstance(b, dict):
                            name += b.get("plain_text", "") or b.get("text", {}).get("content", "")
            if not name:
                name = db_id or "Untitled"
            parent = item.get("parent") or {}
            sources.append({
                "external_source_id": db_id,
                "display_name": name,
                "is_accessible": True,
                "external_parent_id": parent.get("database_id") or parent.get("data_source_id"),
            })
        self._external_sources.upsert_batch(
            connector_instance_id=NOTION_CONNECTOR_INSTANCE_ID,
            owner_user_id=owner_user_id,
            provider="notion",
            sources=sources,
        )
        inst = self._connector_instances.get_by_id(NOTION_CONNECTOR_INSTANCE_ID, owner_user_id)
        if inst:
            now = datetime.now(timezone.utc)
            updated = ConnectorInstance(
                id=inst.id,
                owner_user_id=inst.owner_user_id,
                connector_template_id=inst.connector_template_id,
                display_name=inst.display_name,
                status=inst.status,
                config=inst.config,
                secret_ref=inst.secret_ref,
                visibility=inst.visibility,
                last_validated_at=inst.last_validated_at,
                last_error=None,
                auth_status=inst.auth_status,
                authorized_at=inst.authorized_at,
                disconnected_at=inst.disconnected_at,
                provider_account_id=inst.provider_account_id,
                provider_account_name=inst.provider_account_name,
                last_synced_at=now,
                metadata=inst.metadata or {},
            )
            self._connector_instances.save(updated)
        return sources
