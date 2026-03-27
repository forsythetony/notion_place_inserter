# Quick Start template — sharing the Notion page and testing the flow

**Audience:** You (or anyone running a beta smoke test) who wants to **share** the Oleo Places template and verify **Create Pipeline from Template** end to end.

**Related:** [First pipeline — time to value](./first-pipeline-time-to-value-architecture.md) (product architecture). This note is a **practical checklist** grounded in current code.

---

## What the product does (one sentence)

After **Notion is connected**, Dashboard **Quick Start** calls `POST /management/bootstrap/create-from-template`, which finds a specific Notion **database**, creates the **Oleo Template Pipeline** job, and a **`POST /hello-world`** HTTP trigger (bearer auth). The pipeline runs Google Places research and writes **Name**, **Address**, **Coordinates**, and **Description** into that database.

---

## The important detail: it is the database title, not “page is live”

The backend does **not** care whether a marketing page is public. It uses the Notion API to **search** for a **database / data source** whose **title contains** this substring (case-insensitive):

`Oleo Places Template Database`

That string is the canonical search phrase in [`app/routes/management.py`](../../../../app/routes/management.py) (`TEMPLATE_DB_SEARCH_NAME`).

So for a tester:

1. They must **own a copy** of that database **inside their Notion workspace** (duplicate from your template, or create a DB and name it accordingly).
2. The **Oleo integration** must be **connected to that database** (in Notion: open the database → **Connections** → add the Oleo connection). Without this, search will not return the DB and provisioning fails with a helpful `TEMPLATE_DB_NOT_FOUND` error that lists what the integration *can* see.

**Answering “do I just make it live and send a link?”**

- **Publishing** a page to the web can help people **discover** and **duplicate** your template into their workspace — that is a fine distribution step.
- **By itself**, “live” does not satisfy the app. The tester still needs the **database in their workspace**, with a **matching title substring**, and **shared with the integration**.

---

## Suggested sharing flow for testers

1. **Prepare the template in Notion** — Ensure the **database** (inline or full-page) is titled so it includes `Oleo Places Template Database`, or instruct testers to rename after duplicating. The pipeline expects columns aligned with the template (Name, Address, Coordinates, Description) as documented on the Dashboard Quick Start.
2. **Share** — Send a **Notion duplicate** / template link, or a public page with instructions: “Duplicate into your workspace, then confirm the database title contains `Oleo Places Template Database`.”
3. **Oleo account** — Tester signs up, accepts EULA, etc.
4. **Connect Notion** — **Connections** (or equivalent) in Oleo; complete OAuth.
5. **Grant access to the database** — In Notion, on the duplicated database: **Connections** → add **Oleo** (wording may vary slightly in Notion’s UI).
6. **Create pipeline** — **Dashboard** → **Create Pipeline from Template**.  
   - First success returns `trigger_secret` **once**; copy it immediately.  
   - Calling again is idempotent: if the job already exists, response is `already_exists` and **no new secret** is shown (use **Triggers** in the app to rotate if needed).
7. **Run the trigger** — Either:
   - **Triggers** in the app: use **live test** / invoke for the Hello World trigger (sends `POST` with the right URL and secret), or  
   - `curl` / Postman: `POST` to  
     `{API_BASE_URL}/triggers/{user_id}/hello-world`  
     with header `Authorization: Bearer <trigger_secret>` and JSON body:
     ```json
     { "keywords": "coffee shop near downtown Austin" }
     ```
     (`keywords` is required; length limits apply per `default_keywords_request_body_schema()` in `app/services/trigger_request_body.py`.)

8. **Confirm** — Check **Monitoring** / run history / Notion row updates as you normally would for beta.

---

## Quick troubleshooting

| Symptom | Likely cause |
|--------|----------------|
| **422** `NOTION_NOT_CONNECTED` | Notion OAuth not completed in Oleo. |
| **404** `TEMPLATE_DB_NOT_FOUND` | No database title in the workspace matches the substring, or the integration cannot see any DB (Connections not added on the database). Error payload may list databases/pages the integration *can* see — use that to debug. |
| `already_exists` but no secret | Expected on repeat; secret was only shown on first create. Rotate the trigger secret in Triggers or use the stored secret. |

---

## Code references (for maintainers)

| Piece | Location |
|-------|----------|
| Bootstrap endpoint | `POST /management/bootstrap/create-from-template` — [`management.py`](../../../../app/routes/management.py) `create_pipeline_from_template` |
| Search name | `TEMPLATE_DB_SEARCH_NAME = "Oleo Places Template Database"` |
| Job display name | `TEMPLATE_PIPELINE_DISPLAY_NAME = "Oleo Template Pipeline"` |
| Trigger path | `/hello-world` |
| Dashboard UI | `notion_pipeliner_ui` — [`DashboardPage.tsx`](../../../../../notion_pipeliner_ui/src/routes/DashboardPage.tsx) |

---

## Revision history

| Version | Date | Notes |
|---------|------|-------|
| 1 | 2026-03-27 | Initial runbook: share template DB, integration connection, create-from-template, fire `/hello-world`. |
