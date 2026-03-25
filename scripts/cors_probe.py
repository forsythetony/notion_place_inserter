#!/usr/bin/env python3
"""CORS diagnostic probe.

Sends requests to both the custom-domain URL and the direct Render URL,
then prints the response headers side-by-side so you can compare CORS
behaviour and trace each request by its X-Request-Id.

Usage:
    python scripts/cors_probe.py
"""

import uuid
import requests

# ── URLs to test ────────────────────────────────────────────────────
CUSTOM_DOMAIN_URL = "https://api.oleo.sh"
DIRECT_RENDER_URL = "https://YOUR_SERVICE.onrender.com"  # TODO: set this

# Paths to probe (no auth needed for /health)
PATHS = [
    "/health",
    "/auth/admin/runs?limit=50&offset=0",
    "/management/account",
]

# Origin the browser would send
ORIGIN = "https://oleo.sh"

CORS_HEADERS = [
    "access-control-allow-origin",
    "access-control-allow-methods",
    "access-control-allow-headers",
    "access-control-allow-credentials",
]


def _probe(base_url: str, path: str, method: str = "OPTIONS") -> None:
    url = f"{base_url}{path}"
    request_id = str(uuid.uuid4())

    headers = {
        "Origin": ORIGIN,
        "X-Request-Id": request_id,
    }
    if method == "OPTIONS":
        headers["Access-Control-Request-Method"] = "GET"
        headers["Access-Control-Request-Headers"] = "Authorization, Content-Type"

    print(f"\n{'─' * 70}")
    print(f"  {method} {url}")
    print(f"  X-Request-Id: {request_id}")
    print(f"{'─' * 70}")

    try:
        resp = requests.request(method, url, headers=headers, timeout=10)
    except requests.RequestException as exc:
        print(f"  ERROR: {exc}")
        return

    print(f"  Status: {resp.status_code}")

    # Echo back the request ID the server saw (if it returns one)
    server_rid = resp.headers.get("x-request-id")
    if server_rid:
        print(f"  X-Request-Id (response): {server_rid}")

    # CORS headers
    found_any = False
    for h in CORS_HEADERS:
        val = resp.headers.get(h)
        if val is not None:
            print(f"  {h}: {val}")
            found_any = True
    if not found_any:
        print("  ⚠  No CORS headers in response")

    # Any other interesting headers
    for h in ["server", "cf-ray", "cf-cache-status", "x-render-origin-server"]:
        val = resp.headers.get(h)
        if val:
            print(f"  {h}: {val}")


def main() -> None:
    for base in [CUSTOM_DOMAIN_URL, DIRECT_RENDER_URL]:
        print(f"\n{'═' * 70}")
        print(f"  BASE: {base}")
        print(f"{'═' * 70}")
        for path in PATHS:
            # Preflight (OPTIONS) — this is what the browser actually sends first
            _probe(base, path, method="OPTIONS")
            # Actual GET
            _probe(base, path, method="GET")


if __name__ == "__main__":
    main()
