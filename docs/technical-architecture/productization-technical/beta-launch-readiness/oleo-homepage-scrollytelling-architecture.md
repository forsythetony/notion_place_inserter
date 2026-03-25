# Architecture push: Oleo marketing homepage (scrollytelling)

**Status:** In progress — MVP shipped 2026-03-23 (hero + sections 3/4/7/8; scroll-snap + IO play/pause; reduced motion). **Hero (2026-03-23+):** unified spec implementation in progress — word-origin SVG particles → processor card → fan-out → table (`HeroPipelineSection`, `heroScenes.ts`, `heroMeasure.ts`); vertical stream prototype replaced. Deferred: card stack (§2), AI funnel (§5), notifications (§6), full beta form backend.  
**Audience:** Frontend engineers and design; product for copy alignment  
**Primary code:** [`notion_pipeliner_ui`](../../../../../notion_pipeliner_ui/) — public marketing surface, today [`LandingPage`](../../../../../notion_pipeliner_ui/src/routes/LandingPage.tsx) at `/`  
**Source:** Design & animation architecture draft v1 (PDF *Oleo homepage architecture*, 2026; original working title referenced *Agate / Notion Place Inserter*). Final **public product name** remains governed by [public product name and positioning](./public-product-name-and-positioning.md).

---

## Executive summary

Ship a **single-page, vertical-scroll marketing homepage** that explains the pipeline through **progressive, full-viewport scenes** (scrollytelling), in the spirit of Apple product pages: clean, story-driven, minimal chrome. Motion is **slow and meditative** — never flashy. The page is the primary **beta narrative** surface alongside invitation-led onboarding.

---

## Non-goals

- Replacing authenticated app chrome (`AppShell`) or pipeline editor UX — this doc is **public marketing only**.
- Backend contracts beyond what existing APIs already expose for beta signup or analytics (call those out when implementation starts).

---

## Tech stack (target)

| Layer | Choice |
|-------|--------|
| App | React + Vite (existing `notion_pipeliner_ui` setup) |
| Motion | **GSAP** + **MotionPathPlugin** (register once at app root) |
| Optional React integration | `@gsap/react` (`useGSAP` — HMR-safe cleanup) |
| Paths / hero stage | Inline **SVG** in JSX (no separate asset pipeline required for v1) |
| Depth (card stack) | **CSS** `perspective` + `transform-style: preserve-3d` — no Three.js |
| Glow / particles | **SVG** `feGaussianBlur`; particles as **soft radial-gradient** shapes, not flat dots |

**Dependencies:** `gsap`; optionally `@gsap/react`.

---

## Visual language

| Token | Guidance |
|-------|----------|
| Background | Dark desaturated (~`#12111A`) |
| Typography | Warm white (~`#E8E4DF`) — avoid pure `#fff` |
| Accent / particles | Indigo–violet (~`#6366F1`) |
| Depth | Blur **increases with distance** from focal point (depth of field), not uniform blur |
| Grid / structure | Grid lines read as **light refraction**, not hard rules |
| Motion | **No bounce, no elastic.** Prefer `power1.inOut` or `power2.in` / `power2.out`. **Duration floor ~0.8s** — nothing faster. |
| Loops | Timelines use `repeat: -1` with a **natural pause** between cycles (`repeatDelay`). |

---

## Information architecture — eight sections

Each section is roughly **one viewport**; **scroll-snap** (`scroll-snap-type: y mandatory`) keeps sections aligned. Section animations should **start on `IntersectionObserver` entry** and **pause when the section leaves** the viewport to save CPU/GPU. **`prefers-reduced-motion`:** disable particle-heavy motion; keep layout and readable copy.

### Section 01 — Hero: pipeline at a glance

**Intent:** Before any body copy, show **raw input → processor → structured columns** in a looping, hypnotic animation.

**Layout:** Full viewport; centered composition. **Column headers** span width below the “fold” line of the graphic, e.g. `name`, `place`, `tags`, `location`, `image`. **Tagline** (2–3 sentences) above or beside the graphic — e.g. *“You paste it. We parse it. Notion gets the rest.”*

**Animation phases (loop)**

1. **Input stream (~1.5s)** — Raw text fades in at **top-center** source node. Particles spawn ~every **0.3s**; small **rounded-rectangle** glows (not dots); **feGaussianBlur** trail; easing `power1.inOut` (river-like).
2. **Processor node (~0.3s)** — Particles converge; node **brightness pulse** per particle: `1.0 → 1.5 → 1.0` over **~0.25s**; soft radial gradient only (no hard ring).
3. **Fan-out & column crawl (~2.0s)** — Bezier paths from node to each header, activated **staggered ~0.15s**; particles crawl **ant-like** along paths with **1–2px perpendicular wobble**; column header **dim pulse** on particle arrival.

**Loop:** Fade particles out at columns → **~0.5s** pause → `gsap.timeline({ repeat: -1, repeatDelay: 0.5 })`.

---

### Section 02 — Rotating scenarios (card stack)

**Intent:** Show **3–4 real scenarios** (restaurant, CRM lead, product idea, pipeline-specific demo) using the **same stream metaphor** with different semantic content. Cards are **physically stacked** with depth blur: active card sharp; rear cards progressively softer.

**Scenario content examples (from spec)**

- **Places** — Input e.g. *Danny's Restaurant New York City* → columns name, city, cuisine, rating, coordinates.
- **CRM / sales** — e.g. *John Smith enterprise lead fintech* → company, sector, lead_score, next_action.
- **Ideas / products** — e.g. *biodegradable 3D printing filament* → category, market, materials, competitors, viability.
- **Your pipeline** — e.g. *Izakaya Rintaro, SF, Japanese* → tags, location, notion_page, image (Freepik).

**Depth layers (CSS)**

| Layer | blur | scale | translateZ | opacity |
|-------|------|-------|------------|---------|
| Active | 0 | 1.0 | 0 | 1.0 |
| −1 | 1.5px | 0.95 | −60px | 0.55 |
| −2 | 3px | 0.90 | −120px | 0.28 |

Container: `perspective: 1200px`; `transform-style: preserve-3d`.

**Card transition (~2.5s total)**

- Outgoing: `rotateX(8deg)`, scale **0.94**, `z` **−80px**, opacity **0**, blur **4px**; `power2.in` over **~1.2s** (falls back).
- Incoming: from `rotateX(-6deg)`, scale **0.88**, `z` **−160px**, blur **6px**; `power2.out` over **~1.4s** (rises forward). Slight **rotateX** for physical card feel (not a flat zoom).

**Cell value resolution — character scramble** — On arrival at a column, cell shows **random chars** (A–Z, 0–9, `#@.`); **~8 cycles / 0.3s** then snap to real value; final reveal `opacity 0 → 1` on real text.

**Scene timing rhythm (order-of-magnitude ~9.5s per scene)** — Input fade ~0.8s → stream ~1.5s → processor ~0.3s → fan-out ~1.0s → crawl ~2.0s → scramble resolve ~0.8s → hold populated ~2.0s → card dissolve ~1.2s. Tune in implementation.

---

### Section 03 — Define triggers

**Intent:** Link **mobile trigger** to **web definition**.

**Layout:** Split — **Left:** iOS Share Sheet screen recording or high-fidelity mock — user selects text (e.g. *Nobu, Malibu*), Share → shortcut, confirmation toast; loop cleanly. **Right:** Web app **Triggers** UI with active trigger highlighted; fields e.g. Source, Event Type, Input Format. **Visual link:** animated line or glow from left action to right definition. **Headline:** *Define triggers and connect your apps.* **Sub:** *Anything can start a pipeline. An iOS shortcut, a webhook, a cron job. You define when — [product] handles what happens next.*

---

### Section 04 — Define your pipeline

**Intent:** Show the **pipeline canvas** (or clean schematic): nodes connected by **soft particle streams** (same language as hero). Example nodes: Input → Enrich → Tag → AI Classify → Write to Notion. Inactive/future nodes: dimmer + slight blur; nodes **pulse gently** as particles pass. **Headline:** *Design the way your data flows.* **Sub:** *Build visual pipelines that enrich, classify, and route your data automatically. No code required — but it's all there if you want it.*

---

### Section 05 — Supercharge with AI

**Intent:** **AI property selection** — many options on the left (dense, slightly blurred); **funnel / beam** to one highlighted value on the right. **Headline:** *Supercharge your flow with AI.* **Sub:** *Connect your property definitions and let Claude pick the right value every time…*

---

### Section 06 — Get notified your way

**Intent:** Close the loop from Section 03 — **iPhone home screen** → WhatsApp (or configurable channel) notification → tap → Notion opens to completed page. Sequence: quiet home screen → banner → preview copy e.g. *✓ Nobu Malibu added to your Places database* → expand → second tap → Notion page populated (hold ~2s). **Headline / sub** variants: *Notified your way.* / *When your pipeline completes, you'll know. WhatsApp, Slack, email — pick your channel.*

---

### Section 07 — Integrations constellation

**Intent:** **Not a logo table** — **constellation**: cards in soft grid or arc, faint glow; **featured** integrations brighter/larger; **ambient particle drift** between cards. **Tiers:** featured (center) vs supporting (peripheral). Radial gradient behind cluster for depth.

**Featured cards (spec)**

| Integration | Glow / notes |
|-------------|----------------|
| Google Places | Blue `#4285F4` — location & place data |
| Freepik | Teal/green `#00C27C` — AI imagery for covers |

**Supporting tier (examples)**

| Integration | Glow / notes |
|-------------|----------------|
| Notion | Warm white `#F5F5F0` — destination |
| Claude (Anthropic) | Indigo `#6366F1` — classification |

**Additional mentions:** iOS Shortcuts, WhatsApp, webhooks, Google Sheets, Slack (future), custom scripts (future).

**Card anatomy (~180×120 featured, ~120×80 supporting):** `rgba(255,255,255,0.04)` glass, `1px rgba(255,255,255,0.08)` border, logo ~40px, label ~13px warm white, `box-shadow` with brand color at ~0.15 opacity, **border-radius ≥ 16px**.

**Ambient grid:** slow independent **Y drift** (±4px, ~6s, phase-offset per card); faint **connecting threads** between featured cards, opacity pulse ~0.05 → 0.2 → 0.05 over ~4s; **hover:** brighten card + threads.

**Copy:** *Connects to the tools you already live in.* / *…Google Places enriches… Freepik… Claude… Notion…*

---

### Section 08 — Join the beta

**Intent:** Minimal **early access** form — no feature grid, no pricing. **Fields:** Name, Email, How do you use Notion? (short text), What kind of data do you want to structure?, Developer? (yes / no / sometimes), Checkbox: agree to feedback within 2 weeks. **Headline:** *Request early access.* **Sub:** Private beta, power Notion users, honest feedback in exchange.

Wire to existing **beta / invitation** flows when implemented (may defer to backend endpoints already planned for cohorts).

---

## Implementation checklist (when starting build)

1. Register **MotionPathPlugin** once (e.g. app entry or a `HomepageMotionRoot` provider).
2. **Scroll-snap** on the page wrapper; **IntersectionObserver** per section for play/pause.
3. **Reduced motion** stylesheet / GSAP overrides for `prefers-reduced-motion: reduce`.
4. Keep SVG paths **inline** in JSX unless bundle size forces splitting.
5. Performance budget: pause offscreen timelines; avoid unnecessary repaints on scroll.

---

## Related documents

- [Beta UI general polish](./beta-ui-general-polish.md) — cross-app polish; landing page **visual system** for this homepage should align where shared tokens apply.
- [Public product name and positioning](./public-product-name-and-positioning.md) — final naming and hero copy.
- Pre-token visual direction: [`docs/style/design-direction-options.md`](../../../style/design-direction-options.md) (directional; homepage spec above is **canonical for this page**).

---

## Revision history

| Version | Date | Notes |
|---------|------|-------|
| 1 | 2026-03-23 | Architecture push: PDF draft v1 transcribed into repo; status **Open**. |
