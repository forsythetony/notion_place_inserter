#!/usr/bin/env python3
"""
Issue invitation codes and create users from a CSV file.
- issue-invitations: calls POST /auth/invitations
- create-users: ensures invite exists via POST /auth/invitations, then calls POST /auth/signup
Authenticates via Supabase Auth password grant for admin operations.
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
import typer
from loguru import logger
from supabase import create_client

USER_TYPES = frozenset({"ADMIN", "STANDARD", "BETA_TESTER"})
REQUIRED_HEADERS = frozenset({"userType", "platformIssuedOn", "issueTo", "password"})

app = typer.Typer(help="Issue invitations and create users from CSV via backend API.")


def _get_token(
    supabase_url: str,
    apikey: str,
    email: str,
    password: str,
    timeout: float,
) -> str:
    url = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    resp = httpx.post(
        url,
        headers={"apikey": apikey, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=timeout,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        typer.echo(f"Auth failed: {e.response.status_code} - check username/password", err=True)
        raise typer.Exit(1) from e
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise typer.Exit(1)
    return token


def _load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return []
    headers = set(rows[0].keys())
    missing = REQUIRED_HEADERS - headers
    if missing:
        raise typer.BadParameter(
            f"CSV must have headers {sorted(REQUIRED_HEADERS)}. Missing: {sorted(missing)}"
        )
    return rows


def _validate_row_invitation(row: dict, row_num: int) -> str | None:
    """Return error message if invalid for issue-invitations, else None."""
    ut = (row.get("userType") or "").strip()
    if not ut:
        return "userType is empty"
    if ut not in USER_TYPES:
        return f"userType must be one of {sorted(USER_TYPES)}, got {ut!r}"
    platform = (row.get("platformIssuedOn") or "").strip()
    if not platform:
        return "platformIssuedOn is empty"
    issue_to = (row.get("issueTo") or "").strip()
    if not issue_to:
        return "issueTo is empty"
    return None


def _validate_row_create_user(row: dict, row_num: int) -> str | None:
    """Return error message if invalid for create-users, else None."""
    err = _validate_row_invitation(row, row_num)
    if err:
        return err
    pw = (row.get("password") or "").strip()
    if not pw:
        return "password is empty"
    if len(pw) < 6:
        return "password must be at least 6 characters"
    return None


def _write_results(results: list[dict], output_path: Path | None, prefix: str) -> Path:
    """Write results to JSON file. Returns the path used."""
    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not output_path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = out_dir / f"{prefix}_{ts}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return output_path


def _issue_one(
    client: httpx.Client,
    api_base: str,
    token: str,
    row: dict,
    timeout: float,
) -> tuple[dict | None, str | None]:
    """Issue one invite. Returns (response_json, error_message)."""
    payload = {
        "userType": (row.get("userType") or "").strip(),
        "issuedTo": (row.get("issueTo") or "").strip(),
        "platformIssuedOn": (row.get("platformIssuedOn") or "").strip(),
    }
    url = f"{api_base.rstrip('/')}/auth/invitations"
    try:
        resp = client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json(), None
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        return None, f"HTTP {resp.status_code}: {detail}"
    except httpx.TimeoutException as e:
        return None, f"Timeout: {e}"
    except httpx.RequestError as e:
        return None, f"Request error: {e}"


def _signup_one(
    client: httpx.Client,
    api_base: str,
    email: str,
    password: str,
    code: str,
    timeout: float,
) -> tuple[dict | None, str | None]:
    """Create one user via signup. Returns (response_json, error_message)."""
    payload = {"email": email, "password": password, "code": code}
    url = f"{api_base.rstrip('/')}/auth/signup"
    try:
        resp = client.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json(), None
        try:
            body = resp.json()
            detail = body.get("detail", resp.text)
        except Exception:
            detail = resp.text
        return None, f"HTTP {resp.status_code}: {detail}"
    except httpx.TimeoutException as e:
        return None, f"Timeout: {e}"
    except httpx.RequestError as e:
        return None, f"Request error: {e}"


def _ensure_admin_profile(
    supabase_url: str,
    supabase_secret_key: str,
    token: str,
) -> None:
    """
    Ensure the authenticated user has an ADMIN profile in user_profiles.
    Creates one if missing, so the backend will accept invitation requests.
    """
    client = create_client(supabase_url, supabase_secret_key)
    try:
        user_response = client.auth.get_user(jwt=token)
    except Exception as e:
        logger.warning("ensure_admin_profile: could not get user from token: {}", e)
        typer.echo("Error: Could not resolve user from token", err=True)
        raise typer.Exit(1) from e

    if not user_response or not getattr(user_response, "user", None):
        typer.echo("Error: Could not resolve user from token", err=True)
        raise typer.Exit(1)

    user_id = str(getattr(user_response.user, "id", "") or "")
    if not user_id:
        typer.echo("Error: User ID is empty", err=True)
        raise typer.Exit(1)

    try:
        resp = (
            client.table("user_profiles")
            .select("user_id")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
    except Exception as e:
        logger.exception("ensure_admin_profile: failed to query user_profiles")
        typer.echo(f"Error: Failed to check profile: {e}", err=True)
        raise typer.Exit(1) from e

    if resp.data and len(resp.data) > 0:
        logger.info("Admin profile already exists for user_id={}", user_id[:8] + "...")
        return

    try:
        client.table("user_profiles").upsert(
            {
                "user_id": user_id,
                "user_type": "ADMIN",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()
        logger.info("Created ADMIN profile for user_id={}", user_id[:8] + "...")
        typer.echo("Created missing ADMIN profile for issuer account.")
    except Exception as e:
        logger.exception("ensure_admin_profile: failed to upsert profile")
        typer.echo(f"Error: Failed to create profile: {e}", err=True)
        raise typer.Exit(1) from e


def _common_options(
    csv_path: Path,
    api_base_url: str,
    supabase_url: str,
    supabase_publishable_key: str | None,
    supabase_secret_key: str | None,
    username: str,
    password: str | None,
    timeout_seconds: float,
    output_path: Path | None,
) -> tuple[str, str]:
    """Validate common auth/env and return (apikey, token). Raises on error."""
    if not password:
        typer.echo("Error: --password or INVITATION_ISSUER_PASSWORD is required", err=True)
        raise typer.Exit(1)
    apikey = supabase_publishable_key or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if not apikey:
        typer.echo(
            "Error: SUPABASE_PUBLISHABLE_KEY must be set (e.g. from envs/local.env)",
            err=True,
        )
        raise typer.Exit(1)
    secret_key = supabase_secret_key or os.environ.get("SUPABASE_SECRET_KEY")
    if not secret_key:
        typer.echo(
            "Error: SUPABASE_SECRET_KEY must be set for profile bootstrap (e.g. from envs/local.env)",
            err=True,
        )
        raise typer.Exit(1)
    token = _get_token(
        supabase_url=supabase_url,
        apikey=apikey,
        email=username,
        password=password,
        timeout=timeout_seconds,
    )
    _ensure_admin_profile(supabase_url=supabase_url, supabase_secret_key=secret_key, token=token)
    return apikey, token


@app.command("issue-invitations")
def issue_invitations(
    csv_path: Path = typer.Option(
        ...,
        "--csv-path",
        "-c",
        path_type=Path,
        exists=True,
        help="Path to CSV file (copy from input_template.csv to input_actual.csv)",
    ),
    api_base_url: str = typer.Option(
        "http://localhost:8000",
        "--api-base-url",
        help="Backend API base URL",
    ),
    supabase_url: str = typer.Option(
        "http://127.0.0.1:54321",
        "--supabase-url",
        help="Supabase Auth URL",
    ),
    supabase_publishable_key: str | None = typer.Option(
        None,
        "--supabase-publishable-key",
        envvar="SUPABASE_PUBLISHABLE_KEY",
        help="Supabase anon/publishable key (default from env)",
    ),
    supabase_secret_key: str | None = typer.Option(
        None,
        "--supabase-secret-key",
        envvar="SUPABASE_SECRET_KEY",
        help="Supabase service role key for profile bootstrap (default from env)",
    ),
    username: str = typer.Option(
        "forsythetony@gmail.com",
        "--username",
        "-u",
        help="Admin email for Supabase Auth",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        "-p",
        envvar="INVITATION_ISSUER_PASSWORD",
        help="Admin password (or set INVITATION_ISSUER_PASSWORD)",
    ),
    timeout_seconds: float = typer.Option(
        15.0,
        "--timeout-seconds",
        help="HTTP timeout per request",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output-path",
        "-o",
        path_type=Path,
        help="Output JSON path (default: output/invitations_<timestamp>.json)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate CSV and preview payloads without issuing",
    ),
) -> None:
    """Issue invitation codes from CSV via backend API."""
    logger.info(
        "Config: csv_path={} api_base_url={} supabase_url={} username={} "
        "timeout_seconds={} dry_run={} output_path={} password={} apikey={}",
        csv_path,
        api_base_url,
        supabase_url,
        username,
        timeout_seconds,
        dry_run,
        output_path if output_path else "<default>",
        "***" if password else "<unset>",
        "***" if (supabase_publishable_key or os.environ.get("SUPABASE_PUBLISHABLE_KEY")) else "<unset>",
    )
    rows = _load_rows(csv_path)
    if not rows:
        typer.echo("No rows in CSV.", err=True)
        raise typer.Exit(1)

    validation_errors: list[tuple[int, str]] = []
    valid_rows: list[tuple[int, dict]] = []
    for i, row in enumerate(rows, start=2):
        err = _validate_row_invitation(row, i)
        if err:
            validation_errors.append((i, err))
        else:
            valid_rows.append((i, row))

    if validation_errors:
        for rn, msg in validation_errors:
            typer.echo(f"Row {rn}: {msg}", err=True)
        typer.echo(f"Fix {len(validation_errors)} row(s) and retry.", err=True)
        raise typer.Exit(1)

    if dry_run:
        typer.echo("Dry run: validated CSV, preview payloads:")
        for rn, row in valid_rows:
            payload = {
                "userType": (row.get("userType") or "").strip(),
                "issuedTo": (row.get("issueTo") or "").strip(),
                "platformIssuedOn": (row.get("platformIssuedOn") or "").strip(),
            }
            typer.echo(f"  Row {rn}: {json.dumps(payload)}")
        typer.echo(f"Would issue {len(valid_rows)} invitation(s).")
        return

    _, token = _common_options(
        csv_path, api_base_url, supabase_url, supabase_publishable_key,
        supabase_secret_key, username, password, timeout_seconds, output_path,
    )
    logger.info("Token acquired, issuing invitations...")

    results: list[dict] = []
    successes = 0
    failures = 0

    with httpx.Client() as client:
        for rn, row in valid_rows:
            data, err = _issue_one(
                client=client,
                api_base=api_base_url,
                token=token,
                row=row,
                timeout=timeout_seconds,
            )
            if data:
                results.append({"row": rn, "status": "created", "data": data})
                successes += 1
                typer.echo(f"Row {rn}: created code {data.get('code', '?')}")
            else:
                results.append({"row": rn, "status": "failed", "error": err})
                failures += 1
                typer.echo(f"Row {rn}: failed - {err}", err=True)

    out_path = _write_results(results, output_path, "invitations")
    typer.echo(f"Results written to {out_path}")
    typer.echo(f"Done: {successes} created, {failures} failed")
    if failures:
        raise typer.Exit(1)


@app.command("create-users")
def create_users(
    csv_path: Path = typer.Option(
        ...,
        "--csv-path",
        "-c",
        path_type=Path,
        exists=True,
        help="Path to CSV file (copy from input_template.csv to input_actual.csv)",
    ),
    api_base_url: str = typer.Option(
        "http://localhost:8000",
        "--api-base-url",
        help="Backend API base URL",
    ),
    supabase_url: str = typer.Option(
        "http://127.0.0.1:54321",
        "--supabase-url",
        help="Supabase Auth URL",
    ),
    supabase_publishable_key: str | None = typer.Option(
        None,
        "--supabase-publishable-key",
        envvar="SUPABASE_PUBLISHABLE_KEY",
        help="Supabase anon/publishable key (default from env)",
    ),
    supabase_secret_key: str | None = typer.Option(
        None,
        "--supabase-secret-key",
        envvar="SUPABASE_SECRET_KEY",
        help="Supabase service role key for profile bootstrap (default from env)",
    ),
    username: str = typer.Option(
        "forsythetony@gmail.com",
        "--username",
        "-u",
        help="Admin email for Supabase Auth",
    ),
    password: str | None = typer.Option(
        None,
        "--password",
        "-p",
        envvar="INVITATION_ISSUER_PASSWORD",
        help="Admin password (or set INVITATION_ISSUER_PASSWORD)",
    ),
    timeout_seconds: float = typer.Option(
        15.0,
        "--timeout-seconds",
        help="HTTP timeout per request",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output-path",
        "-o",
        path_type=Path,
        help="Output JSON path (default: output/users_<timestamp>.json)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate CSV and preview signup payloads without creating users",
    ),
) -> None:
    """Create users from CSV: ensure invite exists, then call POST /auth/signup."""
    logger.info(
        "Config: csv_path={} api_base_url={} supabase_url={} username={} "
        "timeout_seconds={} dry_run={} output_path={}",
        csv_path,
        api_base_url,
        supabase_url,
        username,
        timeout_seconds,
        dry_run,
        output_path if output_path else "<default>",
    )
    rows = _load_rows(csv_path)
    if not rows:
        typer.echo("No rows in CSV.", err=True)
        raise typer.Exit(1)

    validation_errors: list[tuple[int, str]] = []
    valid_rows: list[tuple[int, dict]] = []
    for i, row in enumerate(rows, start=2):
        err = _validate_row_create_user(row, i)
        if err:
            validation_errors.append((i, err))
        else:
            valid_rows.append((i, row))

    if validation_errors:
        for rn, msg in validation_errors:
            typer.echo(f"Row {rn}: {msg}", err=True)
        typer.echo(f"Fix {len(validation_errors)} row(s) and retry.", err=True)
        raise typer.Exit(1)

    if dry_run:
        typer.echo("Dry run: validated CSV, preview signup payloads:")
        for rn, row in valid_rows:
            payload = {
                "email": (row.get("issueTo") or "").strip(),
                "password": "***",
                "code": "<obtained from /auth/invitations>",
            }
            typer.echo(f"  Row {rn}: {json.dumps(payload)}")
        typer.echo(f"Would create {len(valid_rows)} user(s).")
        return

    _, token = _common_options(
        csv_path, api_base_url, supabase_url, supabase_publishable_key,
        supabase_secret_key, username, password, timeout_seconds, output_path,
    )
    logger.info("Token acquired, creating users...")

    results: list[dict] = []
    successes = 0
    failures = 0

    with httpx.Client() as client:
        for rn, row in valid_rows:
            email = (row.get("issueTo") or "").strip()
            pw = (row.get("password") or "").strip()

            # Ensure invite exists (idempotent by issuedTo)
            invite_data, invite_err = _issue_one(
                client=client,
                api_base=api_base_url,
                token=token,
                row=row,
                timeout=timeout_seconds,
            )
            if not invite_data:
                results.append({"row": rn, "status": "failed", "stage": "invitation", "error": invite_err})
                failures += 1
                typer.echo(f"Row {rn}: failed to get invite - {invite_err}", err=True)
                continue

            code = invite_data.get("code")
            if not code:
                results.append({"row": rn, "status": "failed", "stage": "invitation", "error": "No code in response"})
                failures += 1
                typer.echo(f"Row {rn}: failed - no code in invite response", err=True)
                continue

            # Create user via signup
            signup_data, signup_err = _signup_one(
                client=client,
                api_base=api_base_url,
                email=email,
                password=pw,
                code=code,
                timeout=timeout_seconds,
            )
            if signup_data:
                results.append({"row": rn, "status": "created", "data": signup_data})
                successes += 1
                typer.echo(f"Row {rn}: created user {signup_data.get('user_id', '?')}")
            else:
                results.append({"row": rn, "status": "failed", "stage": "signup", "error": signup_err})
                failures += 1
                typer.echo(f"Row {rn}: failed signup - {signup_err}", err=True)

    out_path = _write_results(results, output_path, "users")
    typer.echo(f"Results written to {out_path}")
    typer.echo(f"Done: {successes} created, {failures} failed")
    if failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
