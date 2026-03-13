#!/usr/bin/env bash
# Sign in to Supabase Auth and print the access_token.
# Usage: get_auth_token.sh <email> <password>
# Requires: SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL (optional, defaults to local)

set -e

if [ -z "$SUPABASE_PUBLISHABLE_KEY" ]; then
  echo "Error: SUPABASE_PUBLISHABLE_KEY must be set (e.g. from envs/local.env)" >&2
  exit 1
fi

if [ $# -lt 2 ]; then
  echo "Usage: $0 <email> <password>" >&2
  exit 1
fi

EMAIL="$1"
PASSWORD="$2"
SUPABASE_URL="${SUPABASE_URL:-http://127.0.0.1:54321}"
AUTH_URL="${SUPABASE_URL%/}/auth/v1/token?grant_type=password"

RESP=$(curl -s -X POST "$AUTH_URL" \
  -H "apikey: $SUPABASE_PUBLISHABLE_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

if echo "$RESP" | grep -q '"access_token"'; then
  echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
else
  echo "Auth failed:" >&2
  echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP" >&2
  exit 1
fi
