# Notion OAuth App Setup Guide

This guide explains how to create and configure a Notion OAuth integration so users can connect their Notion workspace to the pipeline app.

## Prerequisites

- A Notion account with admin access to create integrations
- Access to the backend environment variables

## Step 1: Create a Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click **"+ New integration"**
3. Fill in:
   - **Name** — e.g. "Pipeline Place Inserter"
   - **Logo** (optional)
   - **Associated workspace** — select your development workspace
4. Under **Capabilities**, enable:
   - **Read content**
   - **Update content**
   - **Insert content**
   - **Read user information** (for workspace context)
5. Click **Submit**

## Step 2: Get Client ID and Client Secret

After creating the integration:

1. On the integration settings page, find **OAuth domain & credentials**
2. Copy the **OAuth client ID** — a UUID like `abc12345-1234-1234-1234-123456789abc`
3. Click **"Show"** next to **OAuth client secret** and copy it — a long string starting with `secret_`

## Step 3: Configure Redirect URI

1. In the same **OAuth domain & credentials** section, find **Redirect URIs**
2. Add your redirect URIs (one per line). The backend callback path is `/auth/callback/notion`; the full URL depends on your environment:

| Environment | Redirect URI |
|------------|--------------|
| Local dev (API on 8000) | `http://localhost:8000/auth/callback/notion` |
| Local dev (custom port) | `http://localhost:<API_PORT>/auth/callback/notion` |
| Staging | `https://<your-staging-api>/auth/callback/notion` |
| Production | `https://<your-production-api>/auth/callback/notion` |

3. Click **Save changes**

**Important:** The redirect URI must match exactly. Trailing slashes, `http` vs `https`, and port differences will cause OAuth to fail.

## Step 4: Set Backend Environment Variables

Configure these in your backend environment (e.g. `.env`, Render, Supabase secrets):

| Variable | Description | Example |
|----------|-------------|---------|
| `NOTION_OAUTH_CLIENT_ID` | OAuth client ID from Step 2 | `abc12345-1234-1234-1234-123456789abc` |
| `NOTION_OAUTH_CLIENT_SECRET` | OAuth client secret from Step 2 | `secret_xxxxxxxxxxxx` |
| `NOTION_OAUTH_REDIRECT_URI` | Must match one of the URIs in Step 3 | `http://localhost:8000/auth/callback/notion` |
| `FRONTEND_BASE_URL` | Base URL of the frontend (for post-callback redirect) | `http://localhost:5173` |

For local development:

```bash
NOTION_OAUTH_CLIENT_ID=your-client-id
NOTION_OAUTH_CLIENT_SECRET=your-client-secret
NOTION_OAUTH_REDIRECT_URI=http://localhost:8000/auth/callback/notion
FRONTEND_BASE_URL=http://localhost:5173
```

## Step 5: Share Databases with the Integration

After a user connects via OAuth, they must share their Notion databases with the integration:

1. Open the Notion database page
2. Click **"..."** (more) in the top right
3. Select **"Add connections"**
4. Choose your integration (e.g. "Pipeline Place Inserter")

Without this step, the integration will not see the database in the source list.

## Callback Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `error=redirect_uri_mismatch` | Redirect URI in Notion does not match `NOTION_OAUTH_REDIRECT_URI` | Add the exact backend callback URL to Notion's Redirect URIs and ensure env var matches |
| `error=invalid_state` | State token expired or already used | User took too long or refreshed; start OAuth again |
| `error=missing_code_or_state` | Notion did not return code/state | User denied access or Notion returned an error; check URL params |
| `oauth_service_unavailable` | Backend not configured | Ensure `NOTION_OAUTH_*` env vars are set and app restarted |
| 503 on OAuth start | OAuth not configured | Set `NOTION_OAUTH_CLIENT_ID`, `NOTION_OAUTH_CLIENT_SECRET`, `NOTION_OAUTH_REDIRECT_URI` |

## Verification

1. Start the backend and frontend
2. Sign in and go to **Connections**
3. Click **Connect Notion**
4. Authorize in Notion
5. You should be redirected back to Connections with the Notion workspace connected
6. Click **Refresh databases** and select databases to use as targets
