# File a Notion Pipeliner app bug

**Invocation:** In Agent chat, type `/` and choose **file-bug** (or start from this command). Paste what you observed, steps to reproduce, and environment; answer any short prompts for missing essentials.

## Goal

Create a **reproducible bug / known-issue** markdown doc for **this product** (Notion Pipeliner: backend `app/`, worker, `notion_pipeliner_ui/`, Supabase-backed behavior)—**not** a production postmortem.

| Use **file-bug** (this command) | Use **incident-investigation** instead |
|--------------------------------|----------------------------------------|
| Wrong UI, API error, pipeline run failure, data looks wrong, flaky behavior in the app | Deploy failure, outage, infra-wide incident, postmortem |

Placement follows `.cursor/rules/docs-placement.mdc`. Bug writeups live next to other tracked issues under:

`docs/technical-architecture/tech-debt/`

Use the same **`td-YYYY-MM-DD-{short-slug}.md`** naming and **`td-…`** ID as existing tech-debt notes (see `td-2026-03-19-pipeline-editor-trigger-layout-after-async-resolve.md`).

## Inputs to collect

Use what the user already supplied; ask only for missing essentials.

| Field | Notes |
|-------|--------|
| **Title** | Short, specific (becomes document H1). |
| **Date** | First seen or filed (YYYY-MM-DD). |
| **Status** | e.g. **Open**, **Backlog**, **Cannot reproduce**, **Fixed in** … |
| **Surface** | **UI** (`notion_pipeliner_ui`), **API** (`app/`), **worker**, **DB/RLS**, **Notion integration**, **multiple**—be explicit. |
| **Environment** | Local dev, staging, production; browser/OS if UI; commit or deploy ref if known. |
| **Steps to reproduce** | Numbered; include URLs, tenant/user context **without** secrets (redact tokens, cookies). |
| **Expected vs actual** | Clear contrast. |
| **Evidence** | Screenshots (describe if not attached), request/response **shapes** (not raw secrets), log lines, correlation IDs. |
| **Severity** | Blocker / major / minor / cosmetic (optional but helpful). |

## Where to write

- **Filename:** `td-{YYYY-MM-DD}-{short-slug}.md`
- **Path:** `docs/technical-architecture/tech-debt/`

## Document skeleton

Match the tone of existing `tech-debt/td-*.md` files. Omit sections that do not apply.

```markdown
# Tech Debt: {Title}

## ID

- `td-{YYYY-MM-DD}-{short-slug}`

## Status

- {Open | Backlog | …}

## Where

- **UI repo / backend / worker:** …
- **Primary files or routes:** … (best-effort; agent may search the repo to refine)

## Observed behavior

- …

## Steps to reproduce

1. …

## Expected behavior

- …

## Why this exists / notes

- Root cause if known; hypotheses if not; **proven vs inferred**.

## Goal

- What “fixed” means (acceptance in plain language).

## Suggested follow-ups

1. …

## Out of scope for this note

- …
```

## After creating the file

1. Add a bullet under **`### tech-debt/`** in the **Architecture document index** in `docs/technical-architecture/work-log.md` — short title, relative link, **Open** — per `.cursor/rules/architecture-doc-index.mdc`.
2. Optionally add a **Log** table row in `work-log.md` if you want a chronological record of “bug filed” (same file as `log-completed-tickets.mdc`); not required for every bug note.

## Hygiene

- Never paste secrets, tokens, or full session cookies; redact or describe source type only.
- If the issue is **security-sensitive** (auth bypass, data leak), flag for the user and avoid putting exploit detail in the doc beyond what’s needed to fix.

## Finish

- Briefly say where the file was written and whether `work-log.md` index was updated.
- **Services to restart:** None (documentation-only).
