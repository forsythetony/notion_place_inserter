# HTTP Get step template — Trafilatura exploration

**Status:** Open (scheduled exploration **2026-03-27**)  
**Type:** Investigation / pre-implementation spec for a new pipeline step template

## Product intent

Add a new step template **HTTP Get** that:

1. **Fetches** a resource over HTTP(S) and surfaces the **response body** as the step output (subject to size/timeout limits to be defined during implementation).
2. Offers an editor control (e.g. **checkbox or toggle**, with copy explaining behavior) that, **when enabled**, runs **main-content extraction** on HTML responses so the stored/output text is **article-like body text** rather than full page chrome, nav, scripts, and boilerplate.

The primary library candidate for (2) is **[Trafilatura](https://trafilatura.readthedocs.io/)** (Python). This document scopes **tomorrow’s exploration**: validate fit, API surface, edge cases, and dependencies before wiring the template end-to-end.

## UI sketch (editor)

- **URL** — text input (required to run the step).
- **Extract main content** (working label) — when **enabled**, pass HTML bodies through Trafilatura (or documented fallback); when **disabled**, pass through raw body (or normalized encoding) as today’s “dumb GET” would.

*Note:* If the product prefers a single “smart” text area that doubles as URL + advanced options, align with [pipeline cell / step detail UI polish](../productization-technical/beta-launch-readiness/pipeline-cell-step-detail-ui-polish.md); this doc does not lock layout.

## Exploration checklist (2026-03-27)

1. **Install & footprint** — `trafilatura` + transitive deps vs worker image size and cold start; optional extras (e.g. faster parsers) if any.
2. **API** — Typical call path: `fetch` HTML string → `trafilatura.extract` / `bare_extraction` / metadata needs; behavior for **non-HTML** (JSON, plain text, binary): no-op vs explicit branch.
3. **Quality** — Spot-check a few real URLs (blog, docs site, heavy nav). Note false negatives (thin content) and false positives.
4. **Failure modes** — Empty extract, encoding errors, very large HTML; align with global limits in [resource limits](../productization-technical/beta-launch-readiness/global-and-per-user-resource-limits.md) where relevant.
5. **Alternatives (light touch)** — One paragraph on **readability-lxml** / **boilerpy3** / raw **BeautifulSoup** heuristics if Trafilatura is unsuitable (no deep shootout unless blocked).
6. **Worker contract** — Where the GET runs (worker-only vs API), timeouts, and how output binds into existing pipeline output surfaces (see [binding picker — output surface metadata](./binding-picker-output-surface-metadata.md)).

## Outcome

- Either **recommend Trafilatura** with concrete function signatures and guardrails, or **reject** with a short rationale and next library to try.
- Update this doc’s **Status** to *Complete on YYYY-MM-DD* and add a **Log** row in [`work-log.md`](./work-log.md) when the exploration is accepted.

## References

- Trafilatura documentation: https://trafilatura.readthedocs.io/
