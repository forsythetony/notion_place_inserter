# Architecture push: Landing page — live demo video (“See it in action”)

**Status:** **Complete on 2026-03-24** · **Ready for review**  
**Audience:** Frontend engineers, design, and whoever records the demo  
**Primary code:** [`notion_pipeliner_ui`](../../../../../notion_pipeliner_ui/) — [`LandingPage`](../../../../../notion_pipeliner_ui/src/routes/LandingPage.tsx) and `src/routes/landing/*` at `/`  
**Related:** [Oleo marketing homepage (scrollytelling)](./oleo-homepage-scrollytelling-architecture.md) (section order and motion language), [Marketing landing page — mobile-friendly](./landing-page-mobile-friendly-architecture.md) (responsive patterns)

---

## Executive summary

Add a **trust-building** block near the **bottom** of the public landing page: a **“See it in action”** section that pairs **honest copy** (this is a real recording, not a mock) with a **looping preview** (GIF or short silent video) and a clear path to a **full-length live demo** (hosted video). The full demo is a **screen recording** in which the founder introduces themselves, walks the major product surfaces, and runs a **live test** (e.g. inserting **places** from unstructured text into Notion).

This push is **GTM-adjacent** but **implementation-owned**: hosting URLs, asset pipeline, layout, modal/accessibility, and performance live in the frontend repo and are tracked here as a **Goal 1 beta gate** item.

---

## Product intent

| Goal | Detail |
|------|--------|
| Trust | Visitors see a **human** and **real behavior**, reducing “vaporware” skepticism before signup or waitlist. |
| Clarity | Copy states explicitly that the **preview loops** a slice of the demo and the **full video** is the complete walkthrough. |
| Conversion | The section sits **late** in the scroll narrative so viewers who reach it are already qualified; **primary CTA** elsewhere (waitlist / auth) remains unchanged unless product decides to add a secondary CTA here. |

---

## Recording (content, not code)

**Owner:** Product / founder (out of band from this repo).

**Run sheet / hosting:** [Beta example demo video — recording and hosting plan](./beta-example-demo-video-recording-and-hosting-plan.md) (deliverables, preferred **Cloudflare R2** upload, `VITE_LANDING_DEMO_*` finish checklist).

Suggested outline for the **full** recording:

1. **Intro** — Name, role, why Oleo exists (short).
2. **Product tour** — Authenticated flows: pipelines, triggers, runs, Notion-facing outcomes, at a pace a new visitor can follow.
3. **Live test** — One concrete path: **unstructured text → place extraction / resolution → records written to Notion** (or the closest canonical “places” story the product supports at beta). No scripted fake data unless labeled.
4. **Outro** — Optional CTA (join waitlist, request access).

**Export:** Master in **MP4 (H.264)**; generate a **short loop** (3–10s) for the inline preview from the same session for visual continuity.

---

## UX specification — “See it in action” section

### Placement

- **Near the bottom** of the landing scroll — **after** the main value-prop and pipeline story blocks, **before** or **directly above** the final beta / waitlist CTA band (exact order should align with [Oleo homepage scrollytelling](./oleo-homepage-scrollytelling-architecture.md) as that doc evolves).
- **One viewport** on desktop (fits the existing full-bleed section pattern); **single column stack** on mobile (see [mobile-friendly landing](./landing-page-mobile-friendly-architecture.md)).

### Layout (desktop)

| Region | Content |
|--------|---------|
| **Left** | **Headline:** “See it in action” (or final marketing string — align with [public product name](./public-product-name-and-positioning.md)). |
| **Left (below headline)** | **Body copy** (2–4 short paragraphs): Sets expectation that this is a **real demo**; mentions **live walkthrough** of features; explicitly calls out **inserting places from unstructured text** (or the agreed canonical example). |
| **Right** | **Preview surface:** looping **GIF** or **muted autoplay video** (`playsInline`, `muted`, `loop`) showing a **representative clip** from the same recording. Entire surface is **clickable** / keyboard-activatable to open the full video. Optional subtle label: “Watch full demo” on hover/focus. |

### Layout (mobile)

- Stack: headline + copy **first**, preview **second** (thumb-friendly; preview not above the fold unless design dictates otherwise).
- **Autoplay:** Respect `prefers-reduced-motion` — show **static poster frame** + “Play full demo” instead of aggressive looping if reduced motion is set.

### Full video presentation

| Option | Pros | Cons |
|--------|------|------|
| **Modal (dialog)** | Keeps user on `/`; familiar pattern | Must handle focus trap, ESC, mobile full-screen feel |
| **Dedicated route** e.g. `/demo` | Shareable URL; simpler a11y tree | Extra page + router entry |

**Recommendation:** Start with a **modal** containing **HTML5 `<video controls>`** or embedded player; add **`/demo`** later if shareability matters.

---

## Technical design

### Asset hosting

| Approach | Notes |
|----------|--------|
| **Static in `public/`** | Simple for MP4/GIF; large files bloat deploy artifacts — acceptable for one hero asset if size-managed. |
| **External CDN** (e.g. R2, S3 + CloudFront, Vimeo, YouTube unlisted) | Better for long-term bandwidth; **URLs in env or a small config map** so production vs staging differ without code changes. |

**Config:** Prefer **`import.meta.env.VITE_*`** (or existing frontend env pattern) for **full video URL** and optional **poster URL**; check in `notion_pipeliner_ui` for conventions.

### Preview format

| Format | Notes |
|--------|--------|
| **GIF** | Easy `<img>`; poor compression; can be heavy — cap dimensions and duration. |
| **MP4 loop** | Prefer **short WebM/MP4** with `loop` + `muted` for quality/size; **poster** image for first paint. |

### Accessibility

- **Full video:** Captions/subtitles if audio narration exists — **WebVTT** sidecar or platform captions if hosted on YouTube/Vimeo.
- **Preview:** `alt` text describing what the loop shows; **keyboard** activation for opening full video; **focus return** on modal close.
- **`prefers-reduced-motion`:** As above — poster + explicit play for full video; avoid infinite distracting loops.

### Performance

- **Lazy load** preview assets when the section enters the viewport (`IntersectionObserver` — same family as existing landing patterns).
- Avoid loading the **full** video until the user opens the modal (unless using a platform iframe that lazy-loads).

---

## Acceptance criteria (beta gate)

1. A **visible section** on `/` matches the **two-column (desktop) / stacked (mobile)** layout with **headline + explanatory copy** and **preview**.
2. **Preview** loops a clip from the real demo; **click / Enter** opens the **full** recording.
3. **Copy** states that the demo is **real** and describes the **places-from-text** story (or the agreed substitute if product changes wording).
4. **Reduced motion** path does not auto-loop a heavy animation in a way that ignores user preference.
5. **Documentation:** This doc’s **Status** updated to **Complete on YYYY-MM-DD** when shipped; Goal 1 + beta hub + architecture index updated. (**Done 2026-03-24.**)

---

## Dependencies

- **Creative:** Recorded master video + derived loop/poster (can be parallel to UI scaffolding with **placeholder** assets).
- **Homepage structure:** Coordinate section order with [Oleo marketing homepage](./oleo-homepage-scrollytelling-architecture.md) so this block does not fight the scroll-snap or CTA narrative.

---

## Revision log

| # | Date | Change |
|---|------|--------|
| 1 | 2026-03-24 | Initial architecture push — live demo section, preview vs full video, hosting and a11y notes; Goal 1 beta tracking. |
| 2 | 2026-03-24 | Shipped in `notion_pipeliner_ui`: `SeeItInActionSection` + `LandingDemoVideoModal`, `landingDemoConfig` / `VITE_LANDING_DEMO_*`, lazy preview via `useSectionInView`, `prefers-reduced-motion` via `usePrefersReducedMotion`, tests + docs/index updates. **Creative:** record master MP4 + short loop/poster and set env (or `public/`) for production. |
