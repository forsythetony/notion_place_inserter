# Oleo Landing Page — Mobile Responsive Architecture

**Document type:** Design & Implementation Spec  
**Scope:** Adapting the existing desktop scrollytelling homepage for mobile viewports (< 768px)  
**Approach:** Progressive enhancement — mobile is the constrained baseline, desktop is the expanded experience. No separate codebase.

---

## Guiding Philosophy

The desktop experience is cinematic and wide. Mobile is intimate and vertical. The goal is not to shrink the desktop layout but to **reimagine each section for a single-column, touch-first context** while preserving the core emotional arc: raw thought → processing → structured data.

Three principles govern every decision below:

1. **Reduce, don't remove.** Every section survives on mobile — just in a distilled form.
2. **Motion earns its keep.** Animations that work at full viewport may feel overwhelming or perform poorly on mobile. Each is evaluated individually.
3. **Thumb zone awareness.** Primary CTAs and interactive elements should sit in the lower two-thirds of the screen where thumbs naturally land.

---

## Breakpoint Strategy

Use a single mobile breakpoint throughout. Do not introduce intermediate tablet breakpoints in this pass — that can come later.

```css
/* Mobile: everything below this is the mobile experience */
@media (max-width: 767px) { ... }

/* Desktop: 768px and above is the existing experience */
@media (min-width: 768px) { ... }
```

The existing CSS is written desktop-first. Mobile overrides go inside `@media (max-width: 767px)` blocks. Do not restructure the existing desktop rules.

---

## Section-by-Section Specification

---

### Section 01 — Hero Pipeline Animation

**The core challenge:** The hero animation was designed around a wide table with 5 columns spanning ~91% of a 1440px viewport. On a 390px iPhone screen, 5 columns at any readable size is physically impossible.

#### Column Reduction

On mobile, reduce from 5 columns to 3. The middle three columns of the existing schema give the strongest narrative signal:

| Desktop column | Mobile | Rationale |
|---|---|---|
| name (title) | ✅ Keep | Always the anchor — who/what this is |
| place (select) | ✅ Keep | The colored pill is visually punchy on small screens |
| tags (multi-select) | ✅ Keep | Two pills side by side demonstrates richness |
| location (relation) | ❌ Drop | Relation icon gets tiny; less visually impactful |
| image/number | ❌ Drop | Monospace number less interesting than the above three |

Update `HERO_COL_COUNT` conditionally, or — better — introduce a `HERO_MOBILE_COLS` constant and a hook that returns the right count based on viewport width. The scene data model already supports 5 values; the mobile render simply ignores columns 4 and 5.

```ts
// heroScenes.ts addition
export const HERO_MOBILE_COL_INDICES = [0, 1, 2]; // name, select, multi-select
```

The table then renders only those 3 columns on mobile, each at `33.33%` width instead of `20%`.

#### Input Text

The existing `clamp(1.75rem, 3.2vw, 3.25rem)` scales down naturally on mobile — at 390px viewport this resolves to roughly `1.75rem`. That's acceptable. No change needed.

However the `max-width: min(92vw, 52rem)` on `.oleo-hero-input-shell--layer` should tighten to `94vw` on mobile so the text uses the full readable width without edge clipping.

#### Processor Card

The processor card at `min(160px, 42vw)` is fine on mobile — `42vw` on a 390px screen gives ~164px, which is actually slightly wider than on desktop. No change needed.

#### Particle Stream

The convergence paths are generated dynamically from measured word positions. On mobile the words wrap to more lines, creating more word-origin points spread vertically. This actually makes the stream look *more* interesting on mobile — denser and more spread out. No code changes needed; the measurement system handles this automatically.

The fan-out paths go to 3 columns instead of 5 — the paths will be less dramatic in their spread but still readable. The `buildFanoutPath` spread calculation uses `columnIndex - 2` as the offset; with 3 columns and indices 0, 1, 2, the spread becomes `(-2, -1, 0) * 12px` — columns fan left of center only. Adjust the center index for 3-column mode:

```ts
// For 3-column mobile mode, center index is 1 not 2
const centerIndex = isMobile ? 1 : 2;
const spread = (columnIndex - centerIndex) * 12;
```

#### Vertical Layout

The absolute positioning of the three layers uses percentage-based `top` values. On mobile these need adjustment because the viewport is taller relative to its width, and the content is more vertically compressed:

```css
@media (max-width: 767px) {
  .oleo-hero-input-shell--layer {
    top: 8%;   /* was 12% — move up slightly, more room below */
  }

  .oleo-hero-processor-card--layer {
    top: 50%;  /* was 52% — similar, minor adjustment */
  }

  .oleo-hero-table-wrap--layer {
    top: 62%;  /* was 60% — push down slightly for 3-col table */
    width: 96%;
  }
}
```

These values should be tuned by eye after implementation — the goal is that all three elements are visible without scrolling within the hero section.

---

### Section 02 — Triggers (Define triggers and connect your apps)

**The core challenge:** The section uses a two-column grid (`1fr 1fr`) with the iOS mock on the left and the web triggers panel on the right. On mobile this must stack vertically.

#### Layout

The existing CSS already has a single-column fallback for `max-width: 880px` — this breakpoint is above 768px, which means the grid already collapses before the mobile breakpoint. **Verify this is working correctly.** If the grid is collapsing at 880px to a single column with the mock on top and the web panel below, mobile should already be handled.

The `.oleo-link-beam` vertical connector only renders at `min-width: 880px` — correct, it should not appear in stacked single-column layout.

#### iOS Mock Width

The mock has `max-width: 380px`. On a 390px screen this means it nearly fills the viewport. Add a `width: 100%` override on mobile so it fills the column container completely:

```css
@media (max-width: 767px) {
  .oleo-mobile-mock-slot {
    width: 100%;
  }

  .oleo-ios-mock-wrap {
    max-width: 100%; /* fill the column on mobile */
  }
}
```

#### Web Triggers Panel

The `.oleo-mock--web` panel stacks below the iOS mock on mobile. This ordering tells the correct story — you see the mobile action first, then the web definition it maps to. No reordering needed.

---

### Section 03 — Pipeline Canvas

**No significant changes needed.** The pipeline schematic already has a responsive CSS rule that switches from horizontal to vertical at `max-width: 640px`:

```css
@media (max-width: 640px) {
  .oleo-pipeline-schematic {
    flex-direction: column;
  }
  .oleo-pipeline-connector {
    width: 2px;
    height: 1.25rem;
  }
}
```

This is correct behavior. The nodes stack vertically with the connectors becoming vertical bars. The animation on the AI classify node continues to work. **Verify on device** that 5 nodes stacked vertically with connectors fit comfortably within the section height without requiring internal scroll.

---

### Section 04 — Integrations Constellation

**The core challenge:** The drifting card grid was designed with enough horizontal space for featured cards to float. On mobile, cards need to wrap into a tighter grid.

#### Featured Cards

At `min-width: 180px` the two featured cards will naturally wrap to their own lines on narrow viewports if the flex container wraps. Currently they're in a flex row with `justify-content: center` — on mobile they'll stack. This is acceptable.

However the minimum height of `120px` means two stacked featured cards consume ~260px of section height before spacing. That's fine given the section is `min-height: 100svh - 52px`.

Consider reducing the minimum height on mobile:

```css
@media (max-width: 767px) {
  .oleo-int-card--featured {
    min-width: 100%;   /* each featured card takes full width */
    min-height: 90px;
  }

  .oleo-int-card--support {
    min-width: calc(50% - 0.625rem); /* 2-column grid for supporting cards */
  }
}
```

#### Drift Animation

The `oleo-card-drift` keyframe animation (slow vertical float) is safe to keep on mobile — it's CSS-only and performs well. No change needed.

#### Constellation Glow

The radial gradient background glow in `.oleo-constellation__glow` is absolute-positioned with `inset: 10% 15%`. On mobile, the section height is taller relative to width — the glow may not center on the cards correctly. Adjust:

```css
@media (max-width: 767px) {
  .oleo-constellation__glow {
    inset: 5% 5%;
  }
}
```

---

### Section 05 — Beta CTA

**Minimal changes needed.** The section is already centered with `text-align: center` and `max-width: 36rem` on the inner container. On a 390px screen, `36rem` is larger than the viewport so it naturally constrains to the viewport width.

The CTA button is `min-height: 48px` which meets the minimum touch target size (Apple HIG recommends 44pt, Google recommends 48dp). No change needed.

Ensure the beta note text at `0.875rem` doesn't overflow on very narrow screens — the `max-width: 28rem` constraint on `.oleo-beta-note` will naturally wrap, which is fine.

---

## Global Mobile Considerations

### Typography Scale

The section titles use `clamp(1.5rem, 2.5vw, 2rem)`. At 390px viewport, `2.5vw` resolves to `9.75px` — the clamp floor of `1.5rem` kicks in, giving `24px` titles. This is fine.

The section sub-copy is `1rem` / `16px` with `line-height: 155%`. Comfortable reading size on mobile. No change.

### Scroll Snap

The existing `scroll-snap-type: y mandatory` means each section snaps into view on scroll. On mobile this can feel aggressive — swiping past a tall section may be difficult if the snap forces you back. Consider relaxing to `proximity` on mobile:

```css
@media (max-width: 767px) {
  .public-content:has(.oleo-homepage) {
    scroll-snap-type: y proximity;
  }
}
```

This lets the user scroll freely but still snaps to sections when close to a snap point. Less trapping.

### Section Minimum Height

`min-height: calc(100svh - 52px)` is appropriate for mobile. `svh` (small viewport height) accounts for the browser chrome appearing and disappearing on scroll, which is critical on mobile where the address bar hides/shows. The existing use of `svh` is correct.

### Touch Targets

All interactive elements in the mock components (`oleo-ios-shortcut-tile__menu`) use `cursor: default` and `pointer-events: none` since they're decorative. Confirm that no accidental tap targets exist within the mocks — iOS share sheet elements in particular should not respond to touch.

---

## Animation Performance on Mobile

Mobile CPUs and GPUs handle composited CSS animations (transform, opacity) well but can struggle with:

- SVG filters (`feGaussianBlur`) on many elements simultaneously
- Backdrop filter (`blur(40px)`) on the iOS mock
- Large numbers of in-flight SVG particles

**Recommended mitigations:**

### Particle Count Reduction

On mobile, reduce spawn frequency for the hero particle stream. The desktop spec calls for spawning every `randomBetween(0.8, 1.4)s` per word. On mobile, increase this to `randomBetween(1.2, 2.0)s` per word — fewer particles in flight at any time:

```ts
const spawnIntervalMin = isMobile ? 1200 : 800;
const spawnIntervalMax = isMobile ? 2000 : 1400;
```

This still reads as a continuous stream but reduces the SVG element count by roughly 40%.

### Backdrop Filter

The iOS mock's `backdrop-filter: blur(40px)` is expensive. On mobile, reduce to `blur(20px)` or remove entirely — the section background is dark enough that the glass effect is less necessary:

```css
@media (max-width: 767px) {
  .oleo-ios-sheet {
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
  }
}
```

### Reduced Motion Respect

The existing `usePrefersReducedMotion` hook already handles the `prefers-reduced-motion: reduce` media query. This is more commonly triggered on mobile (especially by battery-saving modes on Android). The static fallback must look intentional — verify the static hero state is well-composed on a narrow viewport with the 3-column table.

---

## Implementation Order

Work through the sections in this order — each builds confidence before the next:

1. **Global breakpoint setup** — Add the `@media (max-width: 767px)` scroll-snap relaxation and verify all sections are reachable on mobile
2. **Hero column reduction** — Introduce `HERO_MOBILE_COL_INDICES` and the 3-column mobile table render; verify table layout at 390px
3. **Hero vertical positioning** — Tune `top` percentages for the three absolutely positioned layers at mobile viewport height
4. **Hero fan-out center index** — Update `buildFanoutPath` to use the correct center for 3-column mode
5. **Triggers section** — Verify the 880px single-column collapse is working; apply mock width fixes
6. **Integrations** — Apply featured card full-width and supporting 2-column grid
7. **Performance pass** — Apply particle spawn rate reduction and backdrop filter reduction
8. **Device testing** — Test on real devices: iPhone SE (375px), iPhone 14 Pro (393px), Pixel 7 (412px)

---

## Testing Checklist

- [ ] All 5 sections are accessible via scroll on a 375px viewport without horizontal overflow
- [ ] Hero animation plays correctly with 3 columns at mobile viewport size
- [ ] Particles converge and fan out to the correct 3 column positions
- [ ] No text overflows its container at 375px
- [ ] iOS mock does not overflow horizontally
- [ ] More button in destinations row is fully visible
- [ ] Scroll snap feels natural — not trapping
- [ ] Static reduced-motion fallback is well-composed at mobile size
- [ ] Beta CTA button meets 44pt minimum touch target
- [ ] No horizontal scroll at any section
- [ ] Performance: hero animation maintains 60fps on a mid-range Android device (Chrome DevTools CPU 4x throttle as proxy)
