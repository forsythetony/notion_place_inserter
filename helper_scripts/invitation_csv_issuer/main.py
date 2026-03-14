#!/usr/bin/env python3
"""
Issue invitation codes from a CSV file by calling the backend POST /auth/invitations API.
Authenticates via Supabase Auth password grant.
"""

import csv
import json
import os
from pathlib import Path

import httpx
import typer
from loguru import logger

USER_TYPES = frozenset({"ADMIN", "STANDARD", "BETA_TESTER"})
REQUIRED_HEADERS = frozenset({"userType", "platformIssuedOn", "issueTo"})

app = typer.Typer(help="Issue invitation codes from CSV via backend API.")


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


def _validate_row(row: dict, row_num: int) -> str | None:
    """Return error message if invalid, else None."""
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


@app.command()
def run(
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
        help="Output JSON path (default: output/results_<timestamp>.json)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate CSV and preview payloads without issuing",
    ),
) -> None:
    """Issue invitation codes from CSV via backend API."""
    rows = _load_rows(csv_path)
    if not rows:
        typer.echo("No rows in CSV.", err=True)
        raise typer.Exit(1)

    # Validate all rows
    validation_errors: list[tuple[int, str]] = []
    valid_rows: list[tuple[int, dict]] = []
    for i, row in enumerate(rows, start=2):  # row 1 = header
        err = _validate_row(row, i)
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

    logger.info("Fetching access token...")
    token = _get_token(
        supabase_url=supabase_url,
        apikey=apikey,
        email=username,
        password=password,
        timeout=timeout_seconds,
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

    # Write output
    script_dir = Path(__file__).resolve().parent
    out_dir = script_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not output_path:
        from datetime import datetime
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = out_dir / f"results_{ts}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    typer.echo(f"Results written to {output_path}")

    typer.echo(f"Done: {successes} created, {failures} failed")
    if failures:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
