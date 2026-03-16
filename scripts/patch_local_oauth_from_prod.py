#!/usr/bin/env python3
"""
Patch local DB with Notion OAuth credentials from production.

Use when you have an OAuth connection in prod (e.g. forsythetony@gmail.com) but cannot
complete the OAuth callback locally because the redirect URI is configured for the
deployed app. This script copies connector_credentials and connector_instances from
prod into your local Supabase so you can test the full pipeline locally.

Prerequisites:
  - forsythetony@gmail.com exists in local auth.users (create via signup or invite-create-users)
  - envs/prod.env has SUPABASE_URL and SUPABASE_SECRET_KEY for the prod project
  - envs/local.env has SUPABASE_URL and SUPABASE_SECRET_KEY for local (127.0.0.1:54321)

Usage:
  make patch-local-oauth-from-prod
  # or
  python scripts/patch_local_oauth_from_prod.py --email forsythetony@gmail.com
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from loguru import logger
from supabase import create_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROD_ENV = PROJECT_ROOT / "envs" / "prod.env"
LOCAL_ENV = PROJECT_ROOT / "envs" / "local.env"
NOTION_CONNECTOR_ID = "connector_instance_notion_default"


def _get_user_id_by_email(supabase_url: str, service_role_key: str, email: str) -> str | None:
    """Find auth user id by email via GoTrue Admin API."""
    url = f"{supabase_url.rstrip('/')}/auth/v1/admin/users"
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    try:
        page = 1
        per_page = 1000
        while True:
            resp = httpx.get(
                url,
                headers=headers,
                params={"page": page, "per_page": per_page},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            users = data.get("users", [])
            for u in users:
                if (u.get("email") or "").strip().lower() == email.strip().lower():
                    return str(u.get("id", ""))
            if len(users) < per_page:
                break
            page += 1
    except Exception as e:
        logger.warning("auth_admin_list_users_failed | error={}", e)
    return None


def _fetch_prod_credentials(prod_client, owner_user_id: str) -> dict | None:
    """Fetch connector_credentials row for Notion OAuth."""
    r = (
        prod_client.table("connector_credentials")
        .select("*")
        .eq("owner_user_id", owner_user_id)
        .eq("connector_instance_id", NOTION_CONNECTOR_ID)
        .eq("provider", "notion")
        .is_("revoked_at", "null")
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


def _fetch_prod_connector_instance(prod_client, owner_user_id: str) -> dict | None:
    """Fetch connector_instances row for Notion."""
    r = (
        prod_client.table("connector_instances")
        .select("*")
        .eq("id", NOTION_CONNECTOR_ID)
        .eq("owner_user_id", owner_user_id)
        .limit(1)
        .execute()
    )
    rows = r.data or []
    return rows[0] if rows else None


def _upsert_local_credentials(local_client, owner_user_id: str, cred_row: dict) -> None:
    """Upsert connector_credentials into local DB."""
    secret_ref = f"notion_oauth:{owner_user_id}:{NOTION_CONNECTOR_ID}"
    row = {
        "owner_user_id": owner_user_id,
        "connector_instance_id": cred_row["connector_instance_id"],
        "provider": cred_row["provider"],
        "credential_type": cred_row.get("credential_type", "oauth2"),
        "secret_ref": secret_ref,
        "token_payload": cred_row.get("token_payload") or {},
        "token_expires_at": cred_row.get("token_expires_at"),
        "revoked_at": None,
    }
    local_client.table("connector_credentials").upsert(
        row, on_conflict="owner_user_id,connector_instance_id,provider,credential_type"
    ).execute()
    logger.info("patched connector_credentials | owner_user_id={}", owner_user_id)


def _upsert_local_connector_instance(local_client, owner_user_id: str, inst_row: dict) -> None:
    """Upsert connector_instances into local DB."""
    secret_ref = f"notion_oauth:{owner_user_id}:{NOTION_CONNECTOR_ID}"
    row = {
        "id": inst_row["id"],
        "owner_user_id": owner_user_id,
        "connector_template_id": inst_row["connector_template_id"],
        "display_name": inst_row.get("display_name", "Notion"),
        "status": inst_row.get("status", "active"),
        "config": inst_row.get("config") or {},
        "secret_ref": secret_ref,
        "visibility": inst_row.get("visibility", "owner"),
        "auth_status": inst_row.get("auth_status", "connected"),
        "authorized_at": inst_row.get("authorized_at"),
        "disconnected_at": inst_row.get("disconnected_at"),
        "provider_account_id": inst_row.get("provider_account_id"),
        "provider_account_name": inst_row.get("provider_account_name"),
        "last_synced_at": inst_row.get("last_synced_at"),
        "metadata": inst_row.get("metadata") or {},
    }
    local_client.table("connector_instances").upsert(
        row,
        on_conflict="id,owner_user_id",
    ).execute()
    logger.info("patched connector_instances | owner_user_id={}", owner_user_id)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch local DB with Notion OAuth credentials from production."
    )
    parser.add_argument(
        "--email",
        type=str,
        default="forsythetony@gmail.com",
        help="Email of the user with OAuth connection in prod",
    )
    parser.add_argument(
        "--prod-env",
        type=Path,
        default=PROD_ENV,
        help="Path to prod env file",
    )
    parser.add_argument(
        "--local-env",
        type=Path,
        default=LOCAL_ENV,
        help="Path to local env file",
    )
    args = parser.parse_args()

    if not args.prod_env.exists():
        logger.error("Prod env not found: {}", args.prod_env)
        return 1
    if not args.local_env.exists():
        logger.error("Local env not found: {}", args.local_env)
        return 1

    prod_env = dotenv_values(args.prod_env)
    prod_url = (prod_env.get("SUPABASE_URL") or "").strip()
    prod_key = (prod_env.get("SUPABASE_SECRET_KEY") or "").strip()
    if not prod_url or not prod_key:
        logger.error(
            "SUPABASE_URL and SUPABASE_SECRET_KEY required in prod env | path={}",
            args.prod_env,
        )
        return 1

    local_env = dotenv_values(args.local_env)
    local_url = (local_env.get("SUPABASE_URL") or "").strip()
    local_key = (local_env.get("SUPABASE_SECRET_KEY") or "").strip()
    if not local_url or not local_key:
        logger.error(
            "SUPABASE_URL and SUPABASE_SECRET_KEY required in local env | path={}",
            args.local_env,
        )
        return 1

    def _mask_key(k: str) -> str:
        if not k or len(k) < 12:
            return "***" if k else "<empty>"
        return f"{k[:8]}...{k[-4:]}"

    if prod_url == local_url:
        logger.error(
            "prod and local resolve to same SUPABASE_URL | url={} | "
            "Ensure envs/prod.env points to hosted Supabase (e.g. https://<ref>.supabase.co) and "
            "envs/local.env points to local (http://127.0.0.1:54321).",
            prod_url,
        )
        return 1

    logger.info(
        "prod  | path={} SUPABASE_URL={} SUPABASE_SECRET_KEY={}",
        args.prod_env,
        prod_url,
        _mask_key(prod_key),
    )
    logger.info(
        "local | path={} SUPABASE_URL={} SUPABASE_SECRET_KEY={}",
        args.local_env,
        local_url,
        _mask_key(local_key),
    )

    prod_client = create_client(prod_url, prod_key)
    local_client = create_client(local_url, local_key)

    # Find prod user by email
    prod_user_id = _get_user_id_by_email(prod_url, prod_key, args.email)
    if not prod_user_id:
        logger.error(
            "User not found in prod | email={}. Ensure the user exists in prod auth.users.",
            args.email,
        )
        return 1
    logger.info("prod user_id={} | email={}", prod_user_id, args.email)

    # Find local user by email
    local_user_id = _get_user_id_by_email(local_url, local_key, args.email)
    if not local_user_id:
        logger.error(
            "User not found in local | email={}. Create the user first (signup or invite-create-users).",
            args.email,
        )
        return 1
    logger.info("local user_id={} | email={}", local_user_id, args.email)

    # Fetch from prod
    cred = _fetch_prod_credentials(prod_client, prod_user_id)
    if not cred:
        logger.error("No Notion OAuth credentials in prod for user {}", prod_user_id)
        return 1

    inst = _fetch_prod_connector_instance(prod_client, prod_user_id)
    if not inst:
        logger.error("No connector_instance in prod for user {}", prod_user_id)
        return 1

    # Patch into local with local user_id
    _upsert_local_connector_instance(local_client, local_user_id, inst)
    _upsert_local_credentials(local_client, local_user_id, cred)

    logger.info(
        "Done. Sign in locally as {} and test the pipeline.",
        args.email,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
