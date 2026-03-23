# New incident investigation

**Invocation:** In Agent chat, type `/` and choose **incident-investigation** (or start from this command). Paste the incident facts in your message, or answer the agent’s short prompts for anything missing.

## Goal

Create a **production incident / postmortem** markdown doc under:

`docs/technical-architecture/incident_investigations/`

Placement follows `.cursor/rules/docs-placement.mdc` (postmortems and investigations live here, not in feature-proposals).

## Inputs to collect

Use what the user already supplied; ask only for missing essentials.

| Field | Notes |
|-------|--------|
| **Title** | Short, specific (becomes document H1). |
| **Date** | Primary incident or first observation (YYYY-MM-DD). |
| **Status** | e.g. Open, In progress, Mitigated, Complete on YYYY-MM-DD, Reference (incident record). |
| **Severity / impact** | User-facing effect, data, duration, blast radius (optional but encouraged). |
| **Scope and sources** | Logs, dashboards, commits, tickets—state explicitly what this doc is based on. |
| **Timeline** | Detection → response → resolution (or “unknown”). |
| **Observed behavior** | Symptoms, error strings, IDs (redact secrets). |
| **Hypotheses / root cause** | What is proven vs inferred; confidence. |
| **What we ruled out** | If relevant. |
| **Remediation** | Immediate actions + follow-up engineering (link PRs/issues if known). |
| **Recommendations** | Logging, alerts, runbook, tests. |

## Where to write

- **Single writeup:** `short-slug-YYYY-MM-DD.md`
- **Multiple artifacts** (e.g. `logs.txt`, extra notes): subfolder `short-slug_YYYY-MM-DD/` with main file `findings_and_recommendations.md` or `investigation_findings.md` (match existing incidents in that folder).

## Document skeleton

Use `##` sections; omit or merge sections that do not apply—do not leave empty placeholders.

```markdown
# {Title}

**Date:** {YYYY-MM-DD}  
**Status:** {status}

## Scope and sources

- …

## Impact

- …

## Timeline

1. …

## Observed behavior

- …

## Analysis

### Root cause (or leading hypothesis)

…

### What we cannot prove from available evidence

…

## Remediation and follow-up

1. …

## Recommendations (logging / alerts / process)

- …
```

## After creating the file

1. Add a bullet under **`### incident_investigations/`** in `docs/technical-architecture/work-log.md` (Architecture document index): human title, relative link, status—per `.cursor/rules/architecture-doc-index.mdc`.
2. If this work also **closes a shipped ticket**, add a **Log** table row per `.cursor/rules/log-completed-tickets.mdc`. Open investigations often only need the index update.

## Hygiene

- Never paste secrets, tokens, or full session cookies; redact or describe source type only.
- Link related tech-debt or beta-readiness docs when useful.

## Finish

- Briefly say where the file was written and whether `work-log.md` was updated.
- **Services to restart:** None (documentation-only).
