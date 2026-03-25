# Architecture push: Public product name and positioning

**Status:** Complete on 2026-03-24 — public name **Oleo** chosen (positioning copy and legal/domain follow-ups remain)  
**Audience:** Founder, product, and anyone shipping copy, domains, or app chrome before beta  
**Primary surfaces:** [`notion_pipeliner_ui`](../../../../../notion_pipeliner_ui/) — shell brand (`AppShell`, landing), legal/footer strings, future marketing pages

---

## Product vision (context)

Users create **HTTP triggers**, invoke them with a **personalized POST body**, and start a **job**. Jobs have **stages**; stages contain **pipelines**; pipelines call **external APIs** and **AI**; the outcome is **Notion-like pages** (structured content written to the user’s workspace).

This doc tracks **what we call the product** and **how we position it** for Goal 1 (small-group beta), not implementation of triggers or pipelines.

---

## Public name: *Oleo*

**Chosen public name:** *Oleo* (decision recorded 2026-03-24 in [`work-log.md`](../../work-log.md) **Decisions**).

**Etymology / metaphor**

- Spanish **oleoducto** (“oil pipeline”) aligns with “pipeline” as a literal metaphor.
- **Óleo** also means oil (and oil painting in art), so listeners may associate **food, cooking oil, or paint** before “workflow pipeline.”
- The name is short and memorable; positioning copy may need one line clarifying “automation pipelines,” not oil.

**Collision and screening**

- **“Oleo”** is used by several unrelated companies (e.g. industrial rail / energy absorption, cooking-oil recycling, agencies).
- **Deoleo** is a large olive-oil group — similar spelling and category-adjacent noise in web search.
- **Domains (candidate check):** `oleo.ai` appears taken; `oleo.so` was available at last check. **Notion** uses `notion.so`, so a `.so` primary domain may read as aligned with the Notion ecosystem (positioning signal only — re-verify before purchase and check email/DNS deliverability for `.so`). **`oleo.sh`** is another TLD to evaluate: `.sh` often reads as developer/shell/tooling (contrast with `.so`’s Notion-adjacent signal); confirm availability and registrar terms separately.
- **Before beta:** run **domain availability**, **trademark search** in target jurisdictions and classes, and a quick **web/social handle** pass. Record outcomes in **Decisions** or this doc as screening completes.

---

## Deliverables before beta

| Deliverable | Notes |
|-------------|--------|
| **Decision** | **Done:** *Oleo* — see **Decisions** 2026-03-24 in `work-log.md`. |
| **In-product strings** | Align app shell, landing, and auth with chosen name (replace placeholders / internal codenames where user-visible). |
| **Legal / marketing** | If name is final, ensure Privacy/Terms and any beta invite copy use the same string; domain and email-from alignment as feasible. |

---

## Out of scope

- Full **rebrand** (illustration, paid ads, press) — track under marketing when needed.
- **Trademark registration** — product/legal follow-up after screening; not required to close this doc for beta if risk is documented.

---

## Related links

- **Goals:** Goal 1 in [`docs/technical-architecture/work-log.md`](../../work-log.md)
- **Style / voice (when narrative-heavy):** [`docs/style/`](../../../style/) — hub [`README.md`](../../../style/README.md)
