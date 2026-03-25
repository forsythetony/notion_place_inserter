# Landing page — bundled source

This document is a **point-in-time snapshot** (2026-03-23) of the sources that implement the Oleo marketing landing page in `notion_pipeliner_ui`. Edit the source files in the frontend repo; this file is for reference only.

**Source roots:**

- `notion_pipeliner_ui/src/routes/LandingPage.tsx` and `notion_pipeliner_ui/src/routes/landing/`
- Hero dependencies: `src/lib/gsapRegister.ts`, `src/hooks/usePrefersReducedMotion.ts`, `src/hooks/useSectionInView.ts`
- Global Oleo homepage styles: excerpt from `src/App.css` (lines 457–1376; legacy `.landing-page` + full Oleo block through beta CTA)

---

## `src/routes/LandingPage.tsx`

```tsx
import { HeroPipelineSection } from "./landing/HeroPipelineSection";
import { TriggersSection } from "./landing/TriggersSection";
import { PipelineCanvasSection } from "./landing/PipelineCanvasSection";
import { IntegrationsSection } from "./landing/IntegrationsSection";
import { BetaCtaSection } from "./landing/BetaCtaSection";

/**
 * Oleo marketing homepage — scrollytelling MVP (public, all users).
 */
export function LandingPage() {
  return (
    <div className="landing-page oleo-homepage">
      <HeroPipelineSection />
      <TriggersSection />
      <PipelineCanvasSection />
      <IntegrationsSection />
      <BetaCtaSection />
    </div>
  );
}
```

## `src/lib/gsapRegister.ts`

```ts
/**
 * Register GSAP plugins once per bundle. Import this module before any timeline
 * that uses MotionPathPlugin (Oleo homepage hero).
 */
import gsap from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

gsap.registerPlugin(MotionPathPlugin);

export { gsap, MotionPathPlugin };
```

## `src/hooks/usePrefersReducedMotion.ts`

```ts
import { useEffect, useState } from "react";

/**
 * Tracks `prefers-reduced-motion: reduce` for accessible animation fallbacks.
 */
function safeReducedMotionQuery(): boolean {
  if (typeof window === "undefined") return false;
  if (typeof window.matchMedia !== "function") return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(safeReducedMotionQuery);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
```

## `src/hooks/useSectionInView.ts`

```ts
import { useEffect, useRef, useState } from "react";

export type SectionInViewOptions = {
  /** Intersection ratio for firing callbacks. Default 0.15 */
  threshold?: number;
  /** Root margin for IntersectionObserver. Default "0px" */
  rootMargin?: string;
};

/**
 * Observes when a section is in view for play/pause of motion.
 */
export function useSectionInView(options: SectionInViewOptions = {}) {
  const { threshold = 0.15, rootMargin = "0px" } = options;
  const ref = useRef<HTMLElement | null>(null);
  const [inView, setInView] = useState(
    () => typeof IntersectionObserver === "undefined"
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      return;
    }

    const obs = new IntersectionObserver(
      ([entry]) => {
        if (!entry) return;
        setInView(entry.isIntersecting);
      },
      { threshold, rootMargin }
    );

    obs.observe(el);
    return () => obs.disconnect();
  }, [threshold, rootMargin]);

  return { ref, inView };
}
```

## `src/routes/landing/BetaCtaSection.tsx`

```tsx
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/authContext";

/**
 * Section 08 — Join beta. MVP: CTA into existing invite-based `/auth` flow.
 */
export function BetaCtaSection() {
  const { state } = useAuth();
  const authed = state.status === "authenticated";

  return (
    <section className="oleo-section oleo-section--beta" aria-labelledby="oleo-beta-heading">
      <div className="oleo-section__inner oleo-beta-inner">
        <h2 id="oleo-beta-heading" className="oleo-section-title">
          Request early access
        </h2>
        <p className="oleo-section-sub">
          Private beta for power Notion users. We ship fast; you share honest feedback. Sign up with
          your invitation code when you&apos;re ready.
        </p>
        <div className="oleo-beta-actions">
          {authed ? (
            <Link to="/dashboard" className="oleo-cta-btn oleo-cta-btn--primary">
              Open app
            </Link>
          ) : (
            <Link to="/auth" className="oleo-cta-btn oleo-cta-btn--primary">
              Sign in or sign up
            </Link>
          )}
          <p className="oleo-beta-note">
            Beta access uses a 20-character invitation code from your invite email.
          </p>
        </div>
      </div>
    </section>
  );
}
```

## `src/routes/landing/HeroPipelineSection.tsx`

```tsx
import { useRef, useCallback, useEffect } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "../../lib/gsapRegister";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";
import { useSectionInView } from "../../hooks/useSectionInView";
import {
  HERO_COL_COUNT,
  HERO_COLUMN_TYPES,
  HERO_SCENES,
  randomScrambleString,
  type HeroCellValue,
  type HeroSceneNormalized,
} from "./heroScenes";
import { HeroThIcon } from "./heroColumnIcons";
import { buildResolvedCellInnerHtml, getScramblePlainLength } from "./heroNotionCellHtml";
import { HeroResolvedCell } from "./HeroResolvedCell";
import {
  buildConvergencePath,
  buildFanoutPath,
  measureColumnTops,
  measureProcessor,
  measureWordCenters,
  type Point,
  type ProcessorLayout,
} from "./heroMeasure";

/** Floor for Phase 1 — stream must run at least this long before we can end (after spawn stops). */
const CONVERGENCE_MIN_DURATION_MS = 3000;
const PROCESSING_HOLD_MS = 800;
const FANOUT_PATH_STAGGER_MS = 120;
const ROW_HOLD_MS = 2500;
const SCRAMBLE_FRAME_MS = 55;
const SCRAMBLE_TOTAL_MS = 280;
const PROCESSOR_LABELS = ["processing", "enriching", "classifying"] as const;
const CONVERGENCE_START_OFFSET_MS = 800;

function debounce<T extends (...args: unknown[]) => void>(fn: T, ms: number) {
  let t: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (t) clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function splitWords(input: string): string[] {
  return input.trim().split(/\s+/).filter(Boolean);
}

function buildWordSpansHtml(words: string[]): string {
  return words
    .map(
      (w, i) =>
        `<span data-word-index="${i}" class="oleo-hero-word">${w}${i < words.length - 1 ? " " : ""}</span>`
    )
    .join("");
}

function createSvgEl<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {}
): SVGElementTagNameMap[K] {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, v));
  return el;
}

/**
 * Full-viewport hero: word-origin particles → processor card → fan-out → table.
 */
type InputLayer = "a" | "b";

export function HeroPipelineSection() {
  const scopeRef = useRef<HTMLDivElement>(null);
  const inputShellRef = useRef<HTMLDivElement>(null);
  const inputStackRef = useRef<HTMLDivElement>(null);
  const inputTextARef = useRef<HTMLParagraphElement>(null);
  const inputTextBRef = useRef<HTMLParagraphElement>(null);
  /** Which layer currently holds the visible copy (after last transition). */
  const activeInputLayerRef = useRef<InputLayer>("a");
  const processorRef = useRef<HTMLDivElement>(null);
  const processorLabelRef = useRef<HTMLSpanElement>(null);
  const canvasRef = useRef<SVGSVGElement>(null);
  const pathsLayerRef = useRef<SVGGElement>(null);
  const particlesLayerRef = useRef<SVGGElement>(null);
  const dataRowRef = useRef<HTMLTableRowElement>(null);
  const cellRefs = useRef<(HTMLTableCellElement | null)[]>([]);
  const headerRefs = useRef<(HTMLTableCellElement | null)[]>([]);

  const floatTweenRef = useRef<gsap.core.Tween | null>(null);
  const generationRef = useRef(0);
  /** Prevents overlapping scene handoffs if transition is re-entered while a timeline is running. */
  const isTransitioningRef = useRef(false);
  /** Increments on each `loop()` start so two concurrent loops cannot both stay "fresh". */
  const heroLoopRunIdRef = useRef(0);
  const labelIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const reduced = usePrefersReducedMotion();
  const { ref: sectionRef, inView } = useSectionInView({ threshold: 0.12 });
  /** Keep latest visibility for the GSAP loop without putting `inView` in useGSAP deps (avoids restart on threshold flicker). */
  const inViewRef = useRef(inView);
  /** Optional marker for tests: current scene index in the loop (0-based). */
  const heroSceneMarkerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    inViewRef.current = inView;
  }, [inView]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.style.visibility = inView ? "visible" : "hidden";
  }, [inView]);

  /** Pause hero tweens when off-screen; do not tear down the loop (inView is not a useGSAP dependency). */
  useEffect(() => {
    if (reduced) {
      gsap.globalTimeline.pause();
      return;
    }
    if (inView) {
      gsap.globalTimeline.resume();
    } else {
      gsap.globalTimeline.pause();
    }
  }, [inView, reduced]);

  const staticScene = HERO_SCENES[0];

  const setCellRef = useCallback((el: HTMLTableCellElement | null, index: number) => {
    cellRefs.current[index] = el;
  }, []);

  const setHeaderRef = useCallback((el: HTMLTableCellElement | null, index: number) => {
    headerRefs.current[index] = el;
  }, []);

  const stopFloat = useCallback(() => {
    floatTweenRef.current?.kill();
    floatTweenRef.current = null;
    if (inputStackRef.current) gsap.set(inputStackRef.current, { y: 0 });
  }, []);

  const startFloat = useCallback(() => {
    if (!inputStackRef.current) return;
    stopFloat();
    floatTweenRef.current = gsap.to(inputStackRef.current, {
      y: -5,
      duration: 5.5,
      yoyo: true,
      repeat: -1,
      ease: "sine.inOut",
    });
  }, [stopFloat]);

  const stopLabelCycle = useCallback(() => {
    if (labelIntervalRef.current) {
      clearInterval(labelIntervalRef.current);
      labelIntervalRef.current = null;
    }
  }, []);

  const startLabelCycle = useCallback(() => {
    stopLabelCycle();
    let i = 0;
    const el = processorLabelRef.current;
    if (!el) return;
    el.textContent = PROCESSOR_LABELS[0];
    labelIntervalRef.current = setInterval(() => {
      i = (i + 1) % PROCESSOR_LABELS.length;
      const next = PROCESSOR_LABELS[i];
      gsap.to(el, {
        opacity: 0.2,
        duration: 0.3,
        onComplete: () => {
          el.textContent = next;
          gsap.to(el, { opacity: 0.4, duration: 0.3 });
        },
      });
    }, 2500);
  }, [stopLabelCycle]);

  const clearCells = useCallback(() => {
    for (let i = 0; i < HERO_COL_COUNT; i++) {
      const c = cellRefs.current[i];
      if (c) {
        c.innerHTML = "";
        c.className = `oleo-hero-td${HERO_COLUMN_TYPES[i] === "number" ? " oleo-hero-td--number" : ""}`;
        c.classList.remove("oleo-hero-cell--flash", "oleo-hero-cell--populate-glow");
        gsap.set(c, { opacity: 1 });
      }
    }
  }, []);

  const pulseProcessorIntake = useCallback(() => {
    const el = processorRef.current;
    if (!el) return;
    gsap.fromTo(
      el,
      {
        boxShadow: "0 0 32px rgba(99, 102, 241, 0.12)",
        borderColor: "rgba(255, 255, 255, 0.1)",
      },
      {
        boxShadow: "0 0 48px rgba(129, 140, 248, 0.35)",
        borderColor: "rgba(165, 180, 252, 0.35)",
        duration: 0.3,
        yoyo: true,
        repeat: 1,
        ease: "power1.inOut",
        onComplete: () => {
          gsap.set(el, {
            boxShadow: "0 0 32px rgba(99, 102, 241, 0.12)",
            borderColor: "rgba(255, 255, 255, 0.1)",
          });
        },
      }
    );
  }, []);

  const runScrambleCell = useCallback((cell: HTMLTableCellElement, colIndex: number, final: HeroCellValue) => {
    const len = Math.max(getScramblePlainLength(final), 6);
    const frames = Math.max(1, Math.floor(SCRAMBLE_TOTAL_MS / SCRAMBLE_FRAME_MS));
    let frame = 0;

    cell.className = `oleo-hero-td${HERO_COLUMN_TYPES[colIndex] === "number" ? " oleo-hero-td--number" : ""}`;

    gsap.fromTo(
      cell,
      { backgroundColor: "rgba(99, 102, 241, 0)" },
      {
        backgroundColor: "rgba(99, 102, 241, 0.08)",
        duration: 0.15,
        yoyo: true,
        repeat: 1,
        ease: "sine.inOut",
      }
    );

    const step = () => {
      if (frame < frames) {
        cell.textContent = randomScrambleString(len);
        frame++;
        window.setTimeout(step, SCRAMBLE_FRAME_MS);
      } else {
        cell.innerHTML = buildResolvedCellInnerHtml(final);
        gsap.fromTo(cell, { opacity: 0 }, { opacity: 1, duration: 0.25, ease: "power1.out" });
        cell.classList.add("oleo-hero-cell--flash");
        window.setTimeout(() => cell.classList.remove("oleo-hero-cell--flash"), 400);
        gsap.fromTo(
          cell,
          { boxShadow: "inset 0 0 0 rgba(165, 180, 252, 0)" },
          {
            boxShadow: "inset 0 0 16px rgba(165, 180, 252, 0.15)",
            duration: 0.25,
            yoyo: true,
            repeat: 1,
            ease: "sine.inOut",
          }
        );
      }
    };
    step();
  }, []);

  useGSAP(
    () => {
      if (reduced) return undefined;

      const shell = inputShellRef.current;
      const inputStack = inputStackRef.current;
      const textA = inputTextARef.current;
      const textB = inputTextBRef.current;
      const proc = processorRef.current;
      const canvas = canvasRef.current;
      const pathsLayer = pathsLayerRef.current;
      const particlesLayer = particlesLayerRef.current;
      const scope = scopeRef.current;
      if (!shell || !inputStack || !textA || !textB || !proc || !canvas || !pathsLayer || !particlesLayer || !scope) {
        return undefined;
      }
      const pathsLayerEl = pathsLayer;
      const particlesLayerEl = particlesLayer;
      const scopeEl = scope;
      const procEl = proc;

      const getSectionOffset = () => {
        const rect = scopeRef.current?.getBoundingClientRect();
        return { left: rect?.left ?? 0, top: rect?.top ?? 0 };
      };

      const getOutgoingIncoming = () => {
        const active = activeInputLayerRef.current;
        return active === "a"
          ? { out: textA, inc: textB }
          : { out: textB, inc: textA };
      };

      let gen = ++generationRef.current;
      /** Reassigned at each `loop()` start to include a per-loop token (see `heroLoopRunIdRef`). */
      let isStaleFn: () => boolean = () => gen !== generationRef.current;

      const clearParticles = () => {
        while (particlesLayerEl.firstChild) particlesLayerEl.removeChild(particlesLayerEl.firstChild);
      };

      const killAllTweens = () => {
        for (const h of headerRefs.current) {
          if (h) {
            gsap.killTweensOf(h);
            gsap.set(h, { clearProps: "opacity" });
            const label = h.querySelector(".oleo-hero-th__label");
            if (label) gsap.killTweensOf(label);
          }
        }
        for (const n of [
          shell,
          inputStack,
          textA,
          textB,
          procEl,
          dataRowRef.current,
          ...cellRefs.current,
        ]) {
          if (n) gsap.killTweensOf(n);
        }
        transitionRelease?.();
        transitionRelease = null;
        isTransitioningRef.current = false;
      };

      const pendingTimeouts: number[] = [];
      const convTimers: number[] = [];
      /** Resolves the in-flight `transitionBetweenScenes` promise when tweens are killed (invalidate). */
      let transitionRelease: (() => void) | null = null;

      const safeSetTimeout = (fn: () => void, ms: number) => {
        const id = window.setTimeout(() => {
          if (!isStaleFn()) fn();
        }, ms);
        pendingTimeouts.push(id);
        return id;
      };

      const clearPendingTimeouts = () => {
        pendingTimeouts.forEach((id) => clearTimeout(id));
        pendingTimeouts.length = 0;
        convTimers.forEach((id) => clearTimeout(id));
        convTimers.length = 0;
      };

      /** Always settles so async chains do not hang when invalidated mid-wait. */
      const wait = (ms: number) =>
        new Promise<void>((resolve) => {
          if (isStaleFn()) {
            resolve();
            return;
          }
          const id = window.setTimeout(() => {
            resolve();
          }, ms);
          pendingTimeouts.push(id);
        });

      /** Block starting the next scene while the section is off-screen (visibility is not tied to effect teardown). */
      async function waitUntilVisible() {
        while (!inViewRef.current && !isStaleFn()) {
          await wait(100);
        }
      }

      function rebuildPaths(
        words: Point[],
        procLayout: ProcessorLayout,
        cols: Point[],
        viewportCenterX: number
      ) {
        while (pathsLayerEl.firstChild) pathsLayerEl.removeChild(pathsLayerEl.firstChild);
        const conv: SVGPathElement[] = [];
        words.forEach((w, i) => {
          const d = buildConvergencePath(w, procLayout, viewportCenterX);
          const p = createSvgEl("path", {
            d,
            fill: "none",
            stroke: "none",
            "data-conv": String(i),
          }) as SVGPathElement;
          pathsLayerEl.appendChild(p);
          conv.push(p);
        });
        const fan: SVGPathElement[] = [];
        for (let c = 0; c < HERO_COL_COUNT; c++) {
          const d = buildFanoutPath(procLayout, cols[c], c);
          const p = createSvgEl("path", {
            d,
            fill: "none",
            stroke: "none",
            "data-fan": String(c),
          }) as SVGPathElement;
          pathsLayerEl.appendChild(p);
          fan.push(p);
        }
        return { conv, fan };
      }

      function spawnInboundParticle(
        pathEl: SVGPathElement,
        onDone: () => void,
        wordIndex: number,
        wordEls: HTMLElement[],
        onSpawnRecorded?: () => void
      ): boolean {
        if (isStaleFn()) return false;
        onSpawnRecorded?.();

        const g = createSvgEl("g", {}) as SVGGElement;
        particlesLayerEl.appendChild(g);

        const rx = 2 + Math.random() * 3;
        const ry = 3 + Math.random() * 5;
        const bloom = createSvgEl("ellipse", {
          rx: String(12),
          ry: String(18),
          fill: "url(#oleo-hero-grad-inbound)",
          opacity: String(0.07),
        });
        const core = createSvgEl("ellipse", {
          rx: String(rx),
          ry: String(ry),
          fill: "url(#oleo-hero-grad-inbound)",
          opacity: String(0.35 + Math.random() * 0.57),
          filter: "url(#oleo-hero-inbound-blur)",
        });
        g.appendChild(bloom);
        g.appendChild(core);

        const dur = 1.2 + Math.random() * 0.8;
        const tl = gsap.timeline({
          onComplete: () => {
            g.remove();
            onDone();
          },
        });
        tl.to(
          g,
          {
            motionPath: {
              path: pathEl,
              align: pathEl,
              alignOrigin: [0.5, 0.5],
              autoRotate: false,
            },
            duration: dur,
            ease: "none",
          },
          0
        );
        tl.to(g, { scale: 0, opacity: 0, duration: 0.15, ease: "power1.in" }, dur - 0.15);

        const wEl = wordEls[wordIndex];
        if (wEl) {
          gsap.fromTo(
            wEl,
            { opacity: 0.88 },
            { opacity: 1, duration: 0.2, yoyo: true, repeat: 1, ease: "sine.inOut" }
          );
        }
        return true;
      }

      function spawnOutboundParticle(pathEl: SVGPathElement, onArrive: () => void) {
        if (isStaleFn()) return;
        const g = createSvgEl("g", {}) as SVGGElement;
        particlesLayerEl.appendChild(g);

        const rx = 2 + Math.random() * 3;
        const ry = 3 + Math.random() * 5;
        const bloom = createSvgEl("ellipse", {
          rx: String(12),
          ry: String(18),
          fill: "url(#oleo-hero-grad-outbound)",
          opacity: String(0.07),
        });
        const core = createSvgEl("ellipse", {
          rx: String(rx),
          ry: String(ry),
          fill: "url(#oleo-hero-grad-outbound)",
          opacity: String(0.35 + Math.random() * 0.57),
          filter: "url(#oleo-hero-outbound-blur)",
        });
        g.appendChild(bloom);
        g.appendChild(core);

        const dur = 1.0 + Math.random() * 0.8;
        gsap.to(g, {
          motionPath: {
            path: pathEl,
            align: pathEl,
            alignOrigin: [0.5, 0.5],
            autoRotate: false,
          },
          duration: dur,
          ease: "none",
          onComplete: () => {
            g.remove();
            onArrive();
          },
        });
      }

      /**
       * Phase 1 ends only when: (1) minimum duration elapsed and spawning stopped, and
       * (2) every spawned particle has finished (dissolve + onComplete). Stops spawning at min duration
       * so completed can catch spawned.
       */
      function waitConvergencePhaseComplete(): Promise<void> {
        return new Promise<void>((resolve) => {
          let settled = false;
          const settle = () => {
            if (settled) return;
            settled = true;
            resolve();
          };

          const offset = getSectionOffset();
          const vcx = window.innerWidth / 2 - offset.left;
          const rawProc = measureProcessor(procEl);
          const procLayout = rawProc
            ? {
                cx: rawProc.cx - offset.left,
                cy: rawProc.cy - offset.top,
                bx: rawProc.bx - offset.left,
                by: rawProc.by - offset.top,
              }
            : null;
          const wordEls = Array.from(scopeEl.querySelectorAll<HTMLElement>("[data-word-index]"));
          const wordPts = measureWordCenters(scopeEl).map((p) => ({
            x: p.x - offset.left,
            y: p.y - offset.top,
          }));
          const cols = measureColumnTops(scopeEl).map((p) => ({
            x: p.x - offset.left,
            y: p.y - offset.top,
          }));
          if (!procLayout || wordPts.length === 0) {
            settle();
            return;
          }

          const { conv } = rebuildPaths(wordPts, procLayout, cols, vcx);

          let spawned = 0;
          let completed = 0;
          let minDurationElapsed = false;
          let spawningStopped = false;

          const checkAdvance = () => {
            if (isStaleFn()) {
              settle();
              return;
            }
            if (minDurationElapsed && completed >= spawned) {
              settle();
            }
          };

          const stopSpawning = () => {
            spawningStopped = true;
            convTimers.forEach((id) => clearTimeout(id));
            convTimers.length = 0;
          };

          safeSetTimeout(() => {
            if (isStaleFn()) {
              settle();
              return;
            }
            minDurationElapsed = true;
            stopSpawning();
            checkAdvance();
          }, CONVERGENCE_MIN_DURATION_MS);

          conv.forEach((pathEl, wi) => {
            const tick = () => {
              if (isStaleFn() || spawningStopped) return;
              const started = spawnInboundParticle(
                pathEl,
                () => {
                  pulseProcessorIntake();
                  completed++;
                  checkAdvance();
                },
                wi,
                wordEls,
                () => {
                  spawned++;
                }
              );
              if (!started || isStaleFn() || spawningStopped) return;
              const next = 800 + Math.random() * 600;
              convTimers.push(window.setTimeout(tick, next));
            };
            convTimers.push(
              window.setTimeout(() => {
                if (!isStaleFn() && !spawningStopped) tick();
              }, wi * 300)
            );
          });
        });
      }

      async function transitionBetweenScenes(
        prev: HeroSceneNormalized | null,
        next: HeroSceneNormalized,
        onInputWordsMounted?: () => void
      ): Promise<void> {
        if (isStaleFn()) return;
        if (!textA || !textB) return;
        if (isTransitioningRef.current) return;
        isTransitioningRef.current = true;

        const cells = cellRefs.current;
        const headers = headerRefs.current;

        if (prev) {
          gsap.set(inputStack, { opacity: 1 });
          for (let i = HERO_COL_COUNT - 1; i >= 0; i--) {
            const c = cells[i];
            if (c) gsap.to(c, { opacity: 0, duration: 0.1, delay: (HERO_COL_COUNT - 1 - i) * 0.1 });
          }
          await wait(550);

          for (let col = 0; col < HERO_COL_COUNT; col++) {
            const th = headers[col];
            if (!th) continue;
            const labelEl = th.querySelector(".oleo-hero-th__label");
            const oldLabel = labelEl?.textContent ?? "";
            const newLabel = next.columns[col];
            if (oldLabel === newLabel) continue;
            const d = col * 70;
            if (labelEl) {
              gsap.to(labelEl, {
                opacity: 0,
                duration: 0.3,
                delay: d / 1000,
                onComplete: () => {
                  labelEl.textContent = newLabel;
                  gsap.to(labelEl, { opacity: 1, duration: 0.3 });
                },
              });
            }
          }
          await wait(600);
        } else {
          for (let col = 0; col < HERO_COL_COUNT; col++) {
            const th = headers[col];
            if (!th) continue;
            const labelEl = th.querySelector(".oleo-hero-th__label");
            if (labelEl) labelEl.textContent = next.columns[col];
          }
        }

        if (isStaleFn()) {
          isTransitioningRef.current = false;
          return;
        }

        if (!prev) {
          textA.innerHTML = buildWordSpansHtml(splitWords(next.input));
          textB.innerHTML = "";
          activeInputLayerRef.current = "a";
          onInputWordsMounted?.();
          gsap.set(textB, { opacity: 0, y: 0 });
          // Active layer + stack are visible shells; word spans own opacity/y (no parent/child tween fight).
          gsap.set(textA, { opacity: 1, y: 0 });
          gsap.set(inputStack, { opacity: 1, y: 0 });

          await new Promise<void>((resolve) => {
            let settled = false;
            const settle = () => {
              if (settled) return;
              settled = true;
              transitionRelease = null;
              resolve();
            };
            transitionRelease = settle;

            const wordSpans = textA.querySelectorAll<HTMLElement>("[data-word-index]");
            if (wordSpans.length === 0) {
              startFloat();
              settle();
              return;
            }

            gsap.fromTo(
              wordSpans,
              { opacity: 0, y: 8 },
              {
                opacity: 1,
                y: 0,
                duration: 1.2,
                stagger: 0.06,
                ease: "power2.out",
                onComplete: () => {
                  startFloat();
                  settle();
                },
              }
            );
          });
          return;
        }

        const { out, inc } = getOutgoingIncoming();

        await new Promise<void>((resolve) => {
          let settled = false;
          const settle = () => {
            if (settled) return;
            settled = true;
            transitionRelease = null;
            resolve();
          };
          transitionRelease = settle;

          const tl = gsap.timeline({
            onComplete: () => {
              out.innerHTML = "";
              gsap.set(out, { opacity: 0, y: 0 });
              activeInputLayerRef.current = activeInputLayerRef.current === "a" ? "b" : "a";
              startFloat();
              settle();
            },
          });
          // Strict sequence: exit outgoing layer → mount incoming copy → animate incoming (no overlap with exit).
          tl.to(out, { y: -6, opacity: 0, duration: 0.8, ease: "power1.inOut" });
          tl.add(() => {
            inc.innerHTML = buildWordSpansHtml(splitWords(next.input));
            onInputWordsMounted?.();
            gsap.set(inc, { opacity: 0, y: 10 });
          });
          // Container is an instant-visible shell; word spans own opacity/y so no parent/child tween fight.
          tl.add(() => {
            gsap.set(inc, { opacity: 1, y: 0 });
          });
          // `tl.add(fn)` wraps `fn` in delayedCall(0) and **discards** its return value — a returned
          // tween would not extend this timeline, so onComplete fired early and cleared layers while
          // text was still invisible. Add the stagger tween as a real child instead.
          // Nested `tl.add(tween, ">")` inside `tl.add(callback)` never runs — the playhead has
          // already passed that position. delayedCall is a proper timeline child; fromTo runs independently.
          tl.add(
            gsap.delayedCall(0, () => {
              const wordSpans = inc.querySelectorAll<HTMLElement>("[data-word-index]");
              if (wordSpans.length === 0) return;
              gsap.fromTo(
                wordSpans,
                { opacity: 0, y: 8 },
                {
                  opacity: 1,
                  y: 0,
                  duration: 1.2,
                  stagger: 0.06,
                  ease: "power2.out",
                }
              );
            }),
            ">"
          );
        });
      }

      async function playScene(scene: HeroSceneNormalized, prev: HeroSceneNormalized | null) {
        if (isStaleFn()) return;

        clearCells();
        procEl.classList.remove("oleo-hero-processor-card--idle");
        startLabelCycle();
        if (processorLabelRef.current) {
          processorLabelRef.current.textContent = "processing";
          gsap.set(processorLabelRef.current, { opacity: 0.4 });
        }

        let sceneStartForConv = 0;
        await transitionBetweenScenes(prev, scene, () => {
          sceneStartForConv = performance.now();
        });
        if (isStaleFn()) return;
        if (!sceneStartForConv) return;

        await wait(CONVERGENCE_START_OFFSET_MS);
        if (isStaleFn()) return;
        isTransitioningRef.current = false;

        await waitConvergencePhaseComplete();
        if (isStaleFn()) return;

        clearParticles();
        if (isStaleFn()) return;

        await wait(PROCESSING_HOLD_MS);
        if (isStaleFn()) return;

        const offset = getSectionOffset();
        const vcx = window.innerWidth / 2 - offset.left;
        const rawProc = measureProcessor(procEl);
        const procLayout = rawProc
          ? {
              cx: rawProc.cx - offset.left,
              cy: rawProc.cy - offset.top,
              bx: rawProc.bx - offset.left,
              by: rawProc.by - offset.top,
            }
          : null;
        const cols = measureColumnTops(scopeEl).map((p) => ({
          x: p.x - offset.left,
          y: p.y - offset.top,
        }));
        if (!procLayout) return;
        const wordPts = measureWordCenters(scopeEl).map((p) => ({
          x: p.x - offset.left,
          y: p.y - offset.top,
        }));
        const { fan } = rebuildPaths(wordPts, procLayout, cols, vcx);

        const filled = new Array<boolean>(HERO_COL_COUNT).fill(false);
        let firstArrivalAt = -1;

        const schedulePopulate = (col: number, value: HeroCellValue) => {
          const cell = cellRefs.current[col];
          if (!cell) return;
          const now = performance.now();
          if (firstArrivalAt < 0) firstArrivalAt = now;
          const stagger = col * 150 - (now - firstArrivalAt);
          safeSetTimeout(() => {
            if (isStaleFn()) return;
            runScrambleCell(cell, col, value);
          }, Math.max(0, stagger));
        };

        for (let c = 0; c < HERO_COL_COUNT; c++) {
          safeSetTimeout(() => {
            if (isStaleFn() || !fan[c]) return;
            spawnOutboundParticle(fan[c], () => {
              if (filled[c] || isStaleFn()) return;
              filled[c] = true;
              schedulePopulate(c, scene.values[c]);
            });
          }, c * FANOUT_PATH_STAGGER_MS);
        }

        await wait(2800);
        if (isStaleFn()) return;

        clearParticles();
        procEl.classList.add("oleo-hero-processor-card--idle");
        stopLabelCycle();

        await wait(ROW_HOLD_MS);
        if (isStaleFn()) return;

        stopFloat();
        const row = dataRowRef.current;
        if (row) gsap.to(row.querySelectorAll("td"), { opacity: 0, duration: 0.8, ease: "power1.inOut" });

        await wait(900);
        if (isStaleFn()) return;

        clearCells();
        for (let i = 0; i < HERO_COL_COUNT; i++) {
          const c = cellRefs.current[i];
          if (c) gsap.set(c, { opacity: 1 });
        }
      }

      async function loop() {
        const myId = ++heroLoopRunIdRef.current;
        gen = generationRef.current;
        isStaleFn = () => gen !== generationRef.current || myId !== heroLoopRunIdRef.current;
        let prevScene: HeroSceneNormalized | null = null;
        while (!isStaleFn()) {
          await waitUntilVisible();
          if (isStaleFn()) break;
          for (let si = 0; si < HERO_SCENES.length; si++) {
            if (isStaleFn()) break;
            const scene = HERO_SCENES[si];
            heroSceneMarkerRef.current?.setAttribute("data-hero-scene", String(si));
            await playScene(scene, prevScene);
            prevScene = scene;
          }
        }
      }

      let lastObservedW = -1;
      let lastObservedH = -1;

      const onResize = debounce((...args: unknown[]) => {
        const entries = args[0] as ResizeObserverEntry[] | undefined;
        const entry = entries?.[0];
        if (!entry) return;
        const cr = entry.contentRect;
        const w = Math.round(cr.width);
        const h = Math.round(cr.height);
        if (w <= 0 || h <= 0) return;
        if (lastObservedW < 0) {
          lastObservedW = w;
          lastObservedH = h;
          return;
        }
        if (w === lastObservedW && h === lastObservedH) return;
        lastObservedW = w;
        lastObservedH = h;
        generationRef.current += 1;
        clearPendingTimeouts();
        clearParticles();
        stopFloat();
        stopLabelCycle();
        killAllTweens();
        void loop();
      }, 150);

      const ro =
        typeof ResizeObserver !== "undefined" && scopeEl ? new ResizeObserver(onResize) : null;
      if (ro && scopeEl) ro.observe(scopeEl);

      gsap.set(inputStack, { opacity: 0, y: 10 });
      gsap.set([textA, textB], { opacity: 0, y: 0 });
      gsap.set(dataRowRef.current, { opacity: 1 });
      procEl.classList.add("oleo-hero-processor-card--idle");

      void loop();

      return () => {
        generationRef.current += 1;
        ro?.disconnect();
        clearPendingTimeouts();
        clearParticles();
        stopFloat();
        stopLabelCycle();
        killAllTweens();
      };
    },
    {
      scope: scopeRef,
      dependencies: [
        reduced,
        pulseProcessorIntake,
        runScrambleCell,
        startFloat,
        stopFloat,
        stopLabelCycle,
        startLabelCycle,
        clearCells,
      ],
    }
  );

  return (
    <section
      ref={sectionRef}
      className="oleo-section oleo-section--hero oleo-section--hero-v2"
      aria-labelledby="oleo-hero-heading"
    >
      <h1 id="oleo-hero-heading" className="sr-only">
        Oleo
      </h1>

      <div ref={scopeRef} className="oleo-hero-v2">
        <div className="oleo-hero-aurora" aria-hidden />
        <svg className="oleo-hero-noise-svg" aria-hidden>
          <defs>
            <filter id="oleo-hero-noise-filter" x="0%" y="0%" width="100%" height="100%">
              <feTurbulence type="fractalNoise" baseFrequency="0.72" numOctaves="4" seed="42" result="noise" />
              <feColorMatrix type="saturate" values="0" in="noise" />
            </filter>
          </defs>
          <rect width="100%" height="100%" filter="url(#oleo-hero-noise-filter)" opacity={0.04} />
        </svg>

        {reduced ? (
          <div className="oleo-hero-v2__body oleo-hero-v2__body--static">
            <div className="oleo-hero-input-shell oleo-hero-input-shell--static oleo-hero-input-shell--layer">
              <div className="oleo-hero-input-text-stack">
                <p className="oleo-hero-input-text">{staticScene.input}</p>
              </div>
            </div>
            <div
              className="oleo-hero-processor-card oleo-hero-processor-card--static oleo-hero-processor-card--layer"
              aria-hidden
            >
              <div className="oleo-hero-processor-dots oleo-hero-processor-dots--frozen" />
              <span className="oleo-hero-processor-label">processing</span>
            </div>
            <div className="oleo-hero-table-wrap oleo-hero-table-wrap--layer">
              <table className="oleo-hero-table" role="grid" aria-label="Example database row">
                <thead>
                  <tr>
                    {staticScene.columns.map((label, i) => (
                      <th key={i} scope="col" data-column-index={i}>
                        <span className="oleo-hero-th__inner">
                          <span className="oleo-hero-th__icon" aria-hidden>
                            <HeroThIcon type={HERO_COLUMN_TYPES[i]} />
                          </span>
                          <span className="oleo-hero-th__label">{label}</span>
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    {staticScene.values.map((v, i) => (
                      <td
                        key={i}
                        className={
                          HERO_COLUMN_TYPES[i] === "number" ? "oleo-hero-td oleo-hero-td--number" : "oleo-hero-td"
                        }
                      >
                        <HeroResolvedCell value={v} />
                      </td>
                    ))}
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="oleo-reduced-hint">Animation disabled (reduced motion).</p>
          </div>
        ) : (
          <>
            <span
              ref={heroSceneMarkerRef}
              className="sr-only"
              aria-hidden
              data-hero-scene="-1"
            />
            <div className="oleo-hero-v2__body">
              <div ref={inputShellRef} className="oleo-hero-input-shell oleo-hero-input-shell--layer">
                <div ref={inputStackRef} className="oleo-hero-input-text-stack">
                  <p ref={inputTextARef} className="oleo-hero-input-text oleo-hero-input-text--layer" />
                  <p
                    ref={inputTextBRef}
                    className="oleo-hero-input-text oleo-hero-input-text--layer"
                    aria-hidden
                  />
                </div>
              </div>

              <div
                ref={processorRef}
                className="oleo-hero-processor-card oleo-hero-processor-card--layer"
                aria-hidden
              >
                <div className="oleo-hero-processor-dots" aria-hidden>
                  <span />
                  <span />
                  <span />
                </div>
                <span ref={processorLabelRef} className="oleo-hero-processor-label">
                  processing
                </span>
              </div>

              <div className="oleo-hero-table-wrap oleo-hero-table-wrap--layer">
                <table className="oleo-hero-table" role="grid" aria-label="Animated database row">
                  <thead>
                    <tr>
                      {HERO_SCENES[0].columns.map((label, i) => (
                        <th key={i} ref={(el) => setHeaderRef(el, i)} scope="col" data-column-index={i}>
                          <span className="oleo-hero-th__inner">
                            <span className="oleo-hero-th__icon" aria-hidden>
                              <HeroThIcon type={HERO_COLUMN_TYPES[i]} />
                            </span>
                            <span className="oleo-hero-th__label">{label}</span>
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr ref={dataRowRef}>
                      {HERO_SCENES[0].columns.map((_, i) => (
                        <td
                          key={i}
                          ref={(el) => setCellRef(el, i)}
                          className={
                            HERO_COLUMN_TYPES[i] === "number" ? "oleo-hero-td oleo-hero-td--number" : "oleo-hero-td"
                          }
                        />
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <svg ref={canvasRef} className="oleo-hero-canvas" aria-hidden>
              <defs>
                <radialGradient id="oleo-hero-grad-inbound" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#a5b4fc" stopOpacity="1" />
                  <stop offset="100%" stopColor="#a5b4fc" stopOpacity="0" />
                </radialGradient>
                <radialGradient id="oleo-hero-grad-outbound" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#c4b5fd" stopOpacity="1" />
                  <stop offset="100%" stopColor="#c4b5fd" stopOpacity="0" />
                </radialGradient>
                <filter id="oleo-hero-inbound-blur" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="0 3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
                <filter id="oleo-hero-outbound-blur" x="-50%" y="-50%" width="200%" height="200%">
                  <feGaussianBlur in="SourceGraphic" stdDeviation="1.5 3" result="blur" />
                  <feMerge>
                    <feMergeNode in="blur" />
                    <feMergeNode in="SourceGraphic" />
                  </feMerge>
                </filter>
              </defs>
              <g ref={pathsLayerRef} />
              <g ref={particlesLayerRef} />
            </svg>
          </>
        )}
      </div>
    </section>
  );
}
```

## `src/routes/landing/HeroResolvedCell.tsx`

```tsx
import { SELECT_COLORS, type HeroCellValue, type SelectColorKey } from "./heroScenes";

function RelationPageIcon() {
  return (
    <svg width={12} height={12} viewBox="0 0 12 12" fill="none" aria-hidden className="oleo-hero-relation__icon-svg">
      <path d="M2.5 1.5h7v9h-7v-9z" stroke="rgba(255,255,255,0.5)" strokeWidth={1} fill="none" />
      <path d="M4 3.5h4M4 5.5h3" stroke="rgba(255,255,255,0.45)" strokeWidth={0.75} strokeLinecap="round" />
    </svg>
  );
}

/** Static resolved cell (reduced-motion hero table). */
export function HeroResolvedCell({ value }: { value: HeroCellValue }) {
  switch (value.type) {
    case "title":
      return <span className="oleo-hero-cell-title">{value.value}</span>;
    case "select": {
      const c = SELECT_COLORS[value.color] ?? SELECT_COLORS.blue;
      return (
        <span
          className="oleo-hero-pill"
          style={{
            background: c.bg,
            border: `1px solid ${c.border}`,
            color: c.text,
          }}
        >
          {value.value}
        </span>
      );
    }
    case "multi-select":
      return (
        <span className="oleo-hero-multi-wrap">
          {value.value.map((text, i) => {
            const ck: SelectColorKey = value.colors[i] ?? "blue";
            const c = SELECT_COLORS[ck] ?? SELECT_COLORS.blue;
            return (
              <span
                key={`${text}-${i}`}
                className="oleo-hero-pill"
                style={{
                  background: c.bg,
                  border: `1px solid ${c.border}`,
                  color: c.text,
                }}
              >
                {text}
              </span>
            );
          })}
        </span>
      );
    case "relation":
      return (
        <span className="oleo-hero-relation">
          <span className="oleo-hero-relation__icon" aria-hidden>
            <RelationPageIcon />
          </span>
          <span className="oleo-hero-relation__text">{value.value}</span>
        </span>
      );
    case "number":
      return <span className="oleo-hero-cell-number">{value.value}</span>;
  }
}
```

## `src/routes/landing/IntegrationsSection.tsx`

```tsx
import type { CSSProperties } from "react";

/**
 * Section 07 — Integrations constellation. MVP: featured + supporting cards, ambient CSS drift.
 */
const FEATURED = [
  { name: "Google Places", hint: "Location & place data", color: "#4285F4" },
  { name: "Freepik", hint: "Imagery for covers", color: "#00C27C" },
];

const SUPPORTING = [
  { name: "Notion", color: "#F5F5F0" },
  { name: "Claude", color: "#6366F1" },
  { name: "iOS Shortcuts", color: "rgba(232,228,223,0.85)" },
  { name: "Webhooks", color: "rgba(232,228,223,0.65)" },
];

export function IntegrationsSection() {
  return (
    <section
      className="oleo-section oleo-section--integrations"
      aria-labelledby="oleo-int-heading"
    >
      <div className="oleo-section__inner">
        <p className="oleo-eyebrow">Integrations</p>
        <h2 id="oleo-int-heading" className="oleo-section-title">
          Connects to the tools you already live in.
        </h2>
        <p className="oleo-section-sub">
          Google Places enriches addresses, Freepik adds imagery, Claude classifies fields, and Notion
          is the destination — with room for more channels over time.
        </p>

        <div className="oleo-constellation">
          <div className="oleo-constellation__glow" aria-hidden />
          <div className="oleo-constellation__featured">
            {FEATURED.map((card, i) => (
              <div
                key={card.name}
                className="oleo-int-card oleo-int-card--featured oleo-int-card--drift"
                style={
                  {
                    "--oleo-int-glow": card.color,
                    "--oleo-drift-phase": `${i * 0.8}s`,
                  } as CSSProperties
                }
              >
                <div className="oleo-int-card__logo" aria-hidden />
                <div className="oleo-int-card__label">{card.name}</div>
                <div className="oleo-int-card__hint">{card.hint}</div>
              </div>
            ))}
          </div>
          <div className="oleo-constellation__support">
            {SUPPORTING.map((card, i) => (
              <div
                key={card.name}
                className="oleo-int-card oleo-int-card--support oleo-int-card--drift"
                style={
                  {
                    "--oleo-int-glow": card.color,
                    "--oleo-drift-phase": `${i * 0.5 + 0.3}s`,
                  } as CSSProperties
                }
              >
                <div className="oleo-int-card__logo oleo-int-card__logo--sm" aria-hidden />
                <div className="oleo-int-card__label">{card.name}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
```

## `src/routes/landing/PipelineCanvasSection.tsx`

```tsx
import { Fragment } from "react";

/**
 * Section 04 — Pipeline canvas schematic. MVP: nodes + soft connectors (CSS).
 */
const NODES = [
  { id: "in", label: "Input" },
  { id: "enrich", label: "Enrich" },
  { id: "tag", label: "Tag" },
  { id: "ai", label: "AI classify" },
  { id: "out", label: "Write to Notion" },
];

export function PipelineCanvasSection() {
  return (
    <section
      className="oleo-section oleo-section--pipeline"
      aria-labelledby="oleo-pipeline-heading"
    >
      <div className="oleo-section__inner">
        <p className="oleo-eyebrow">Visual flows</p>
        <h2 id="oleo-pipeline-heading" className="oleo-section-title">
          Design the way your data flows.
        </h2>
        <p className="oleo-section-sub">
          Build visual pipelines that enrich, classify, and route your data automatically. No code
          required — but it&apos;s all there if you want it.
        </p>

        <div className="oleo-pipeline-schematic" role="img" aria-label="Pipeline: Input to Notion">
          {NODES.map((n, i) => (
            <Fragment key={n.id}>
              {i > 0 ? (
                <div className="oleo-pipeline-connector" aria-hidden>
                  <span className="oleo-pipeline-stream" />
                </div>
              ) : null}
              <div
                className={`oleo-pipeline-node ${i === 3 ? "oleo-pipeline-node--pulse" : ""} ${i === 1 || i === 4 ? "oleo-pipeline-node--dim" : ""}`}
              >
                <span>{n.label}</span>
              </div>
            </Fragment>
          ))}
        </div>
      </div>
    </section>
  );
}
```

## `src/routes/landing/TriggersSection.tsx`

```tsx
import { MobileMockSlot } from "./mocks/MobileMockSlot";

/**
 * Section 03 — Define triggers (mobile → web). MVP: split layout + schematic link line.
 */
export function TriggersSection() {
  return (
    <section
      className="oleo-section oleo-section--triggers"
      aria-labelledby="oleo-triggers-heading"
    >
      <div className="oleo-section__inner oleo-split">
        <div className="oleo-split__col">
          <p className="oleo-eyebrow">Mobile → automation</p>
          <h2 id="oleo-triggers-heading" className="oleo-section-title">
            Define triggers and connect your apps.
          </h2>
          <p className="oleo-section-sub">
            Anything can start a pipeline — an iOS Shortcut, a webhook, a cron job. You define when;
            Oleo handles what happens next.
          </p>
          <MobileMockSlot />
        </div>
        <div className="oleo-split__col oleo-split__col--link">
          <div className="oleo-link-beam" aria-hidden />
          <div className="oleo-mock oleo-mock--web" aria-hidden>
            <div className="oleo-mock__title">Triggers</div>
            <div className="oleo-mock__field">
              <span>Source</span>
              <strong>HTTP</strong>
            </div>
            <div className="oleo-mock__field">
              <span>Path</span>
              <strong>/locations</strong>
            </div>
            <div className="oleo-mock__field oleo-mock__field--active">
              <span>Status</span>
              <strong>Active</strong>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
```

## `src/routes/landing/heroColumnIcons.tsx`

```tsx
import type { HeroColumnType } from "./heroScenes";

const iconClass = "oleo-hero-th__svg";

/** 12×12 muted icons — quiet hint beside header label. */
export function HeroThIcon({ type }: { type: HeroColumnType }) {
  switch (type) {
    case "title":
      return (
        <svg className={iconClass} viewBox="0 0 12 12" width={12} height={12} aria-hidden>
          <path
            d="M3 2.5h6M3 5h5M3 7.5h6"
            stroke="currentColor"
            strokeWidth="1"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
      );
    case "select":
      return (
        <svg className={iconClass} viewBox="0 0 12 12" width={12} height={12} aria-hidden>
          <circle cx="6" cy="6" r="2.25" fill="currentColor" />
        </svg>
      );
    case "multi-select":
      return (
        <svg className={iconClass} viewBox="0 0 12 12" width={12} height={12} aria-hidden>
          <circle cx="5" cy="4.5" r="1.75" fill="currentColor" opacity="0.85" />
          <circle cx="7" cy="7.5" r="1.75" fill="currentColor" />
        </svg>
      );
    case "relation":
      return (
        <svg className={iconClass} viewBox="0 0 12 12" width={12} height={12} aria-hidden>
          <circle cx="4.5" cy="5" r="2" stroke="currentColor" strokeWidth="1" fill="none" />
          <circle cx="7.5" cy="7" r="2" stroke="currentColor" strokeWidth="1" fill="none" />
        </svg>
      );
    case "number":
      return (
        <svg className={iconClass} viewBox="0 0 12 12" width={12} height={12} aria-hidden>
          <text
            x="6"
            y="9"
            textAnchor="middle"
            fontSize="9"
            fontWeight="500"
            fill="currentColor"
            fontFamily="system-ui, sans-serif"
          >
            #
          </text>
        </svg>
      );
  }
}
```

## `src/routes/landing/heroMeasure.ts`

```ts
/** Viewport-space points for SVG motion paths (getBoundingClientRect). */

export type Point = { x: number; y: number };

export function measureWordCenters(root: Element): Point[] {
  return Array.from(root.querySelectorAll("[data-word-index]")).map((el) => {
    const rect = el.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
  });
}

/** Top center of each column header (for fan-out arrival). */
export function measureColumnTops(root: Element): Point[] {
  return Array.from(root.querySelectorAll("[data-column-index]")).map((el) => {
    const rect = el.getBoundingClientRect();
    return { x: rect.left + rect.width / 2, y: rect.top };
  });
}

export type ProcessorLayout = {
  /** Center — convergence target */
  cx: number;
  cy: number;
  /** Bottom center — fan-out origin */
  bx: number;
  by: number;
};

export function measureProcessor(el: Element | null): ProcessorLayout | null {
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  return {
    cx: rect.left + rect.width / 2,
    cy: rect.top + rect.height / 2,
    bx: rect.left + rect.width / 2,
    by: rect.bottom,
  };
}

/** Quadratic bezier: word → processor center; control pulls to viewport horizontal center. */
export function buildConvergencePath(
  word: Point,
  proc: ProcessorLayout,
  viewportCenterX: number
): string {
  const { cx, cy } = proc;
  return `M ${word.x} ${word.y} Q ${viewportCenterX} ${word.y + 100} ${cx} ${cy}`;
}

/**
 * Cubic bezier from processor bottom to column header top.
 * Outer columns get stronger horizontal pull to reduce crossing.
 */
export function buildFanoutPath(proc: ProcessorLayout, col: Point, columnIndex: number): string {
  const { bx, by } = proc;
  const spread = (columnIndex - 2) * 12;
  const c1x = bx + spread * 0.4;
  const c1y = by + 80;
  const c2x = col.x - spread * 0.35;
  const c2y = col.y - 80;
  return `M ${bx} ${by} C ${c1x} ${c1y} ${c2x} ${c2y} ${col.x} ${col.y}`;
}
```

## `src/routes/landing/heroNotionCellHtml.ts`

```ts
import { SELECT_COLORS, type HeroCellValue, type SelectColorKey } from "./heroScenes";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function selectStyle(color: SelectColorKey): string {
  const c = SELECT_COLORS[color] ?? SELECT_COLORS.blue;
  return `background:${c.bg};border:1px solid ${c.border};color:${c.text}`;
}

/** Plain-text length for scramble (same charset noise for all types). */
export function getScramblePlainLength(v: HeroCellValue): number {
  switch (v.type) {
    case "title":
    case "select":
    case "relation":
    case "number":
      return v.value.length;
    case "multi-select":
      return Math.max(v.value.join(" ").length, 6);
  }
}

/** Resolved cell markup — icons for relation appear only after scramble (not during). */
export function buildResolvedCellInnerHtml(v: HeroCellValue): string {
  switch (v.type) {
    case "title":
      return `<span class="oleo-hero-cell-title">${escapeHtml(v.value)}</span>`;
    case "select": {
      const st = selectStyle(v.color);
      return `<span class="oleo-hero-pill" style="${st}">${escapeHtml(v.value)}</span>`;
    }
    case "multi-select": {
      const pills = v.value.map((text, i) => {
        const col = v.colors[i] ?? "blue";
        const st = selectStyle(col);
        return `<span class="oleo-hero-pill" style="${st}">${escapeHtml(text)}</span>`;
      });
      return `<span class="oleo-hero-multi-wrap">${pills.join("")}</span>`;
    }
    case "relation":
      return `<span class="oleo-hero-relation"><span class="oleo-hero-relation__icon" aria-hidden="true">${RELATION_PAGE_ICON_SVG}</span><span class="oleo-hero-relation__text">${escapeHtml(v.value)}</span></span>`;
    case "number":
      return `<span class="oleo-hero-cell-number">${escapeHtml(v.value)}</span>`;
  }
}

const RELATION_PAGE_ICON_SVG = `<svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M2.5 1.5h7v9h-7v-9z" stroke="rgba(255,255,255,0.5)" stroke-width="1" fill="none"/><path d="M4 3.5h4M4 5.5h3" stroke="rgba(255,255,255,0.45)" stroke-width="0.75" stroke-linecap="round"/></svg>`;
```

## `src/routes/landing/heroScenes.ts`

```ts
/**
 * Oleo hero loop — each scene: input, five column labels, fixed column types, five typed cell values.
 * Column count is always exactly five (see normalizeHeroScene).
 */

export const HERO_COL_COUNT = 5;

/** Fixed order across all scenes — only labels and values change. */
export const HERO_COLUMN_TYPES = ["title", "select", "multi-select", "relation", "number"] as const;
export type HeroColumnType = (typeof HERO_COLUMN_TYPES)[number];

export const SELECT_COLORS = {
  red: { bg: "rgba(239,68,68,0.15)", border: "rgba(239,68,68,0.3)", text: "rgba(239,68,68,0.9)" },
  blue: { bg: "rgba(99,102,241,0.15)", border: "rgba(99,102,241,0.3)", text: "rgba(99,102,241,0.9)" },
  green: { bg: "rgba(34,197,94,0.15)", border: "rgba(34,197,94,0.3)", text: "rgba(34,197,94,0.9)" },
  orange: { bg: "rgba(249,115,22,0.15)", border: "rgba(249,115,22,0.3)", text: "rgba(249,115,22,0.9)" },
  pink: { bg: "rgba(236,72,153,0.15)", border: "rgba(236,72,153,0.3)", text: "rgba(236,72,153,0.9)" },
  purple: { bg: "rgba(168,85,247,0.15)", border: "rgba(168,85,247,0.3)", text: "rgba(168,85,247,0.9)" },
  yellow: { bg: "rgba(234,179,8,0.15)", border: "rgba(234,179,8,0.3)", text: "rgba(234,179,8,0.9)" },
} as const;

export type SelectColorKey = keyof typeof SELECT_COLORS;

export type HeroValueTitle = { type: "title"; value: string };
export type HeroValueSelect = { type: "select"; value: string; color: SelectColorKey };
export type HeroValueMultiSelect = {
  type: "multi-select";
  value: string[];
  colors: SelectColorKey[];
};
export type HeroValueRelation = { type: "relation"; value: string };
export type HeroValueNumber = { type: "number"; value: string };

export type HeroCellValue =
  | HeroValueTitle
  | HeroValueSelect
  | HeroValueMultiSelect
  | HeroValueRelation
  | HeroValueNumber;

export type HeroSceneRaw = {
  input: string;
  columns: string[];
  types: HeroColumnType[];
  values: HeroCellValue[];
};

export type HeroSceneNormalized = {
  input: string;
  columns: [string, string, string, string, string];
  types: [HeroColumnType, HeroColumnType, HeroColumnType, HeroColumnType, HeroColumnType];
  values: [HeroCellValue, HeroCellValue, HeroCellValue, HeroCellValue, HeroCellValue];
};

const PAD_COL = "field";
const PAD_VAL_TITLE: HeroValueTitle = { type: "title", value: "—" };

function warnScene(sceneIndex: number, message: string) {
  console.warn(`[HeroPipelineSection] Scene ${sceneIndex}: ${message}`);
}

/** Pad or truncate to five columns/types/values; log if incoming length ≠ 5. */
export function normalizeHeroScene(raw: HeroSceneRaw, sceneIndex: number): HeroSceneNormalized {
  const { input, columns: colsIn, types: typesIn, values: valsIn } = raw;

  if (
    colsIn.length !== HERO_COL_COUNT ||
    typesIn.length !== HERO_COL_COUNT ||
    valsIn.length !== HERO_COL_COUNT
  ) {
    warnScene(
      sceneIndex,
      `expected ${HERO_COL_COUNT} columns, types, and values; got ${colsIn.length} columns, ${typesIn.length} types, ${valsIn.length} values — padding or truncating.`
    );
  }

  const columns = [...colsIn] as string[];
  const values = [...valsIn] as HeroCellValue[];

  while (columns.length < HERO_COL_COUNT) columns.push(PAD_COL);
  while (values.length < HERO_COL_COUNT) values.push(PAD_VAL_TITLE);

  if (columns.length > HERO_COL_COUNT) columns.length = HERO_COL_COUNT;
  if (values.length > HERO_COL_COUNT) values.length = HERO_COL_COUNT;

  if (typesIn.length !== HERO_COL_COUNT) {
    warnScene(sceneIndex, `expected ${HERO_COL_COUNT} types — padding/truncating types array for validation only.`);
  }
  for (let i = 0; i < HERO_COL_COUNT; i++) {
    if (typesIn[i] !== HERO_COLUMN_TYPES[i]) {
      warnScene(
        sceneIndex,
        `column ${i} authored type "${typesIn[i] ?? ""}" does not match fixed schema "${HERO_COLUMN_TYPES[i]}".`
      );
    }
    values[i] = coerceValueToColumnType(values[i], HERO_COLUMN_TYPES[i], sceneIndex, i);
  }

  return {
    input,
    columns: columns as HeroSceneNormalized["columns"],
    types: [...HERO_COLUMN_TYPES],
    values: values as HeroSceneNormalized["values"],
  };
}

function coerceValueToColumnType(
  v: HeroCellValue,
  expected: HeroColumnType,
  sceneIndex: number,
  col: number
): HeroCellValue {
  if (v.type === expected) {
    if (v.type === "multi-select") {
      const vals = [...v.value];
      const cols = [...v.colors];
      const n = Math.max(vals.length, cols.length, 1);
      while (vals.length < n) vals.push("—");
      while (cols.length < n) cols.push("blue");
      const m = Math.min(vals.length, cols.length);
      return {
        type: "multi-select",
        value: vals.slice(0, m),
        colors: cols.slice(0, m) as SelectColorKey[],
      };
    }
    return v;
  }
  warnScene(sceneIndex, `column ${col}: value type "${v.type}" mismatched expected "${expected}" — coerced.`);
  const s =
    v.type === "multi-select"
      ? v.value.join(", ")
      : v.type === "title" || v.type === "select" || v.type === "relation" || v.type === "number"
        ? v.value
        : "";
  switch (expected) {
    case "title":
      return { type: "title", value: s || "—" };
    case "select":
      return { type: "select", value: s || "—", color: "blue" };
    case "multi-select":
      return {
        type: "multi-select",
        value: s ? s.split(",").map((x) => x.trim()) : ["—"],
        colors: ["blue"],
      };
    case "relation":
      return { type: "relation", value: s || "—" };
    case "number":
      return { type: "number", value: s || "0" };
    default:
      return { type: "title", value: s || "—" };
  }
}

const HERO_SCENES_RAW: HeroSceneRaw[] = [
  {
    input: "Danny's Restaurant, NYC — notes + photo URL",
    columns: ["name", "place", "tags", "location", "image"],
    types: [...HERO_COLUMN_TYPES],
    values: [
      { type: "title", value: "Danny's" },
      { type: "select", value: "Italian", color: "red" },
      { type: "multi-select", value: ["Date Night", "West Village"], colors: ["purple", "blue"] },
      { type: "relation", value: "New York City" },
      { type: "number", value: "4.7" },
    ],
  },
  {
    input: "John Smith, enterprise fintech lead, followed up twice",
    columns: ["name", "company", "sector", "pipeline", "next action"],
    types: [...HERO_COLUMN_TYPES],
    values: [
      { type: "title", value: "John Smith" },
      { type: "select", value: "Stripe", color: "blue" },
      { type: "multi-select", value: ["Fintech", "Enterprise"], colors: ["green", "yellow"] },
      { type: "relation", value: "Q3 Pipeline" },
      { type: "number", value: "87" },
    ],
  },
  {
    input: "biodegradable 3D printing filament, startup idea",
    columns: ["name", "category", "market", "competitors", "viability"],
    types: [...HERO_COLUMN_TYPES],
    values: [
      { type: "title", value: "Bio-Filament" },
      { type: "select", value: "Materials", color: "orange" },
      { type: "multi-select", value: ["Consumer", "Maker"], colors: ["blue", "purple"] },
      { type: "relation", value: "Bambu, Prusa" },
      { type: "number", value: "92%" },
    ],
  },
  {
    input: "Izakaya Rintaro, SF — best omakase I've had",
    columns: ["name", "place", "tags", "location", "image"],
    types: [...HERO_COLUMN_TYPES],
    values: [
      { type: "title", value: "Izakaya Rintaro" },
      { type: "select", value: "Japanese", color: "pink" },
      { type: "multi-select", value: ["Omakase", "SF Pick"], colors: ["red", "yellow"] },
      { type: "relation", value: "Mission District" },
      { type: "number", value: "$$$" },
    ],
  },
];

export const HERO_SCENES: HeroSceneNormalized[] = HERO_SCENES_RAW.map((raw, i) => normalizeHeroScene(raw, i));

/** Spec: A–Z, a–z, 0–9, plus # . _ @ */
const SCRAMBLE_CHARS =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#._@";

export function randomScrambleString(length: number): string {
  let s = "";
  for (let i = 0; i < length; i++) {
    s += SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
  }
  return s;
}
```

## `src/routes/landing/mocks/IosShareSheetMock.tsx`

```tsx
/**
 * IosShareSheetMock: renders a native iOS Share Sheet fragment
 * showing the Oleo shortcut tile as the active destination.
 *
 * Visual reference: iOS 17 Share Sheet, Shortcuts row.
 * Replace this file (and swap the import in MobileMockSlot) to change platforms.
 */
import type { ReactNode } from "react";
import "./IosShareSheetMock.css";

type DestinationItem =
  | { label: string; icon: ReactNode }
  | { isMore: true };

const DESTINATIONS: DestinationItem[] = [
  {
    label: "AirDrop",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" opacity="0.62">
        <circle cx="12" cy="15" r="2" fill="white" />
        <path
          d="M7.5 12.5 C7.5 9.5 16.5 9.5 16.5 12.5"
          stroke="white"
          strokeWidth="1.75"
          strokeLinecap="round"
          fill="none"
        />
        <path
          d="M5 10 C5 5.5 19 5.5 19 10"
          stroke="white"
          strokeWidth="1.75"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
    ),
  },
  {
    label: "Messages",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" opacity="0.62">
        <path
          d="M4 5.5 C4 4.4 4.9 3.5 6 3.5 L18 3.5 C19.1 3.5 20 4.4 20 5.5 L20 14.5 C20 15.6 19.1 16.5 18 16.5 L9 16.5 L5.5 20 L6 16.5 C4.9 16.5 4 15.6 4 14.5 Z"
          stroke="white"
          strokeWidth="1.75"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    ),
  },
  {
    label: "Mail",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" opacity="0.62">
        <rect
          x="3"
          y="6"
          width="18"
          height="13"
          rx="2"
          stroke="white"
          strokeWidth="1.75"
          fill="none"
        />
        <path
          d="M3 7 L12 13.5 L21 7"
          stroke="white"
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    ),
  },
  {
    label: "Notes",
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" opacity="0.62">
        <path
          d="M5 3.5 L16 3.5 L20 7.5 L20 20.5 C20 21.1 19.6 21.5 19 21.5 L5 21.5 C4.4 21.5 4 21.1 4 20.5 L4 4.5 C4 3.9 4.4 3.5 5 3.5 Z"
          stroke="white"
          strokeWidth="1.75"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M16 3.5 L16 7.5 L20 7.5"
          stroke="white"
          strokeWidth="1.75"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M8 11.5 L16 11.5 M8 14.5 L14 14.5"
          stroke="white"
          strokeWidth="1.75"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
    ),
  },
  { isMore: true },
];

export function IosShareSheetMock() {
  return (
    <div className="oleo-ios-mock-wrap">
      <div className="oleo-ios-bg" aria-hidden>
        <div className="oleo-ios-bg__overlay" />

        <div className="oleo-ios-imessage">
          <div className="oleo-ios-bubble oleo-ios-bubble--out">
            yeah i&apos;ll be flying in tomorrow. should be in the area
          </div>

          <div className="oleo-ios-bubble oleo-ios-bubble--in">
            <span className="oleo-ios-bg__selected">
              <span className="oleo-ios-selection-handle oleo-ios-selection-handle--left" />
              Swan Oyster Depot on Polk Street
              <span className="oleo-ios-selection-handle oleo-ios-selection-handle--right" />
            </span>, oh my gosh you gotta check it out
          </div>
        </div>
      </div>

      <div className="oleo-ios-sheet">
        <div className="oleo-ios-sheet__handle" aria-hidden />

        <div className="oleo-ios-sheet__destinations" aria-hidden>
          {DESTINATIONS.map((dest, i) => (
            <div key={i} className="oleo-ios-dest">
              {"isMore" in dest && dest.isMore ? (
                <div className="oleo-ios-dest__more" aria-hidden>
                  •••
                </div>
              ) : (
                <div className="oleo-ios-dest__icon">{dest.icon}</div>
              )}
              {"label" in dest && dest.label ? (
                <span className="oleo-ios-dest__label">{dest.label}</span>
              ) : null}
            </div>
          ))}
        </div>

        <p className="oleo-ios-sheet__section-label">Shortcuts</p>

        <div className="oleo-ios-spotlight-overlay" aria-hidden />

        <div className="oleo-ios-shortcut-tile">
          <button className="oleo-ios-shortcut-tile__menu" aria-hidden tabIndex={-1}>
            •••
          </button>
          <div className="oleo-ios-shortcut-tile__icon" aria-hidden>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
              <path d="M14 3L25 14L14 25L14 17L3 14L14 3Z" fill="white" opacity="0.9" />
            </svg>
          </div>
          <span className="oleo-ios-shortcut-tile__name">Send to Oleo</span>
        </div>
      </div>
    </div>
  );
}
```

## `src/routes/landing/mocks/IosShareSheetMock.css`

```css
/* IosShareSheetMock.css
   All styles scoped to the iOS Share Sheet mock.
   Safe to delete entirely when swapping to a different platform mock. */

.oleo-ios-mock-wrap {
  position: relative;
  width: 100%;
  max-width: 380px;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.oleo-ios-bg {
  position: relative;
  width: 100%;
  padding: 20px 16px 24px;
  background: rgba(0, 0, 0, 0.85);
}

.oleo-ios-bg::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: linear-gradient(to bottom, transparent, rgba(28, 28, 30, 0.97));
  pointer-events: none;
  z-index: 3;
}

.oleo-ios-bg__overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.52);
  pointer-events: none;
  z-index: 1;
}

.oleo-ios-imessage {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.oleo-ios-bubble {
  max-width: 75%;
  padding: 9px 13px;
  font-size: 14px;
  line-height: 1.4;
  font-weight: 400;
  border-radius: 18px;
  word-break: break-word;
  opacity: 0.72;
}

.oleo-ios-bubble--out {
  align-self: flex-end;
  background: #1d82f5;
  color: rgba(255, 255, 255, 0.92);
  border-bottom-right-radius: 5px;
}

.oleo-ios-bubble--in {
  align-self: flex-start;
  background: rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.85);
  border-bottom-left-radius: 5px;
}

.oleo-ios-bg__selected {
  position: relative;
  display: inline;
  background: rgba(10, 132, 255, 0.45);
  border-radius: 2px;
  color: rgba(255, 255, 255, 0.95);
  padding: 1px 0;
  white-space: nowrap;
}

.oleo-ios-selection-handle {
  position: absolute;
  width: 2px;
  top: 0;
  bottom: 0;
  background: #0a84ff;
}

.oleo-ios-selection-handle--left {
  left: -3px;
}

.oleo-ios-selection-handle--right {
  right: -3px;
}

.oleo-ios-selection-handle--left::before {
  content: "";
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0a84ff;
  top: -4px;
  left: 50%;
  transform: translateX(-50%);
}

.oleo-ios-selection-handle--right::after {
  content: "";
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #0a84ff;
  bottom: -4px;
  left: 50%;
  transform: translateX(-50%);
}

.oleo-ios-sheet {
  position: relative;
  z-index: 4;
  width: 100%;
  margin-top: -14px;
  background: rgba(28, 28, 30, 0.97);
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
  border-radius: 14px 14px 16px 16px;
  padding: 12px 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  box-sizing: border-box;
}

.oleo-ios-sheet__handle {
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.25);
  margin: 0 auto;
}

.oleo-ios-sheet__destinations {
  display: flex;
  gap: 20px;
  justify-content: flex-start;
  margin-left: -16px;
  margin-right: -16px;
  padding-left: 16px;
  padding-right: 20px;
  overflow-x: auto;
  overflow-y: hidden;
  -ms-overflow-style: none;
  scrollbar-width: none;
  width: 100%;
  box-sizing: border-box;
}

.oleo-ios-sheet__destinations::-webkit-scrollbar {
  display: none;
}

.oleo-ios-dest {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}

.oleo-ios-dest__icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.12),
    inset 0 -1px 0 rgba(0, 0, 0, 0.2),
    0 2px 4px rgba(0, 0, 0, 0.25);
}

.oleo-ios-dest__more {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.5);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.05em;
  flex-shrink: 0;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    inset 0 -1px 0 rgba(0, 0, 0, 0.15);
}

.oleo-ios-dest__label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.35);
  text-align: center;
  letter-spacing: 0.01em;
}

.oleo-ios-sheet__section-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.3);
  text-transform: uppercase;
  letter-spacing: 0.07em;
  padding: 0 4px;
  margin: 0;
}

.oleo-ios-spotlight-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: calc(100px + 20px);
  background: rgba(0, 0, 0, 0.28);
  pointer-events: none;
  border-radius: 14px 14px 0 0;
  z-index: 1;
}

.oleo-ios-shortcut-tile {
  position: relative;
  z-index: 2;
  width: 100%;
  height: 100px;
  border-radius: 18px;
  background: linear-gradient(135deg, #ff6b35 0%, #ff9a42 100%);
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  padding: 14px 16px;
  overflow: hidden;
  box-sizing: border-box;
}

.oleo-ios-shortcut-tile::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50%;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.12), transparent);
  border-radius: 18px 18px 0 0;
  pointer-events: none;
}

.oleo-ios-shortcut-tile__menu {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.22);
  border: none;
  color: white;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.05em;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: default;
  line-height: 1;
}

.oleo-ios-shortcut-tile__icon {
  position: absolute;
  top: 14px;
  left: 16px;
  opacity: 0.9;
}

.oleo-ios-shortcut-tile__name {
  font-size: 16px;
  font-weight: 700;
  color: white;
  letter-spacing: -0.01em;
  line-height: 1;
  position: relative;
  z-index: 1;
}
```

## `src/routes/landing/mocks/MobileMockSlot.tsx`

```tsx
/**
 * MobileMockSlot — swappable mobile device mock for the Triggers section.
 *
 * To change the mock (e.g. switch to Android):
 *   1. Create a new mock component in ./mocks/
 *   2. Replace the import below with the new component
 *   3. Touch nothing else
 */
import { IosShareSheetMock } from "./IosShareSheetMock";
import "./MobileMockSlot.css";

export function MobileMockSlot() {
  return (
    <div className="oleo-mobile-mock-slot" aria-hidden>
      <IosShareSheetMock />
    </div>
  );
}
```

## `src/routes/landing/mocks/MobileMockSlot.css`

```css
/* MobileMockSlot.css — layout only, no visual opinions */
.oleo-mobile-mock-slot {
  width: 100%;
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
}
```

## `src/App.css` (Oleo homepage excerpt, lines 457–1376)

```css
/* Landing page (legacy minimal; Oleo homepage overrides below) */
.landing-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1.5rem;
  padding: 2rem;
  flex-grow: 1;
}

.landing-page h1 {
  margin: 0;
}

.landing-page .subtitle {
  margin: 0;
  color: var(--text-secondary);
}

/* —— Oleo marketing homepage (scrollytelling MVP) —— */
.public-content:has(.oleo-homepage) {
  padding: 0;
  background: #12111a;
  color: #e8e4df;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
  flex: 1;
  min-height: 0;
  max-height: calc(100svh - 52px);
}

@media (prefers-reduced-motion: reduce) {
  .public-content:has(.oleo-homepage) {
    scroll-behavior: auto;
    scroll-snap-type: y proximity;
  }
}

.public-layout:has(.oleo-homepage) .public-top-bar {
  background: rgba(18, 17, 26, 0.92);
  border-bottom-color: rgba(255, 255, 255, 0.08);
}

.landing-page.oleo-homepage {
  --oleo-bg: #12111a;
  --oleo-text: #e8e4df;
  --oleo-muted: rgba(232, 228, 223, 0.72);
  --oleo-accent: #6366f1;
  margin: 0;
  width: 100%;
  max-width: none;
  padding: 0;
  flex-grow: 1;
  align-items: stretch;
  gap: 0;
}

.oleo-section {
  scroll-snap-align: start;
  scroll-snap-stop: always;
  min-height: calc(100svh - 52px);
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 2.5rem 1.5rem 3rem;
  box-sizing: border-box;
}

@media (max-width: 720px) {
  .oleo-section {
    min-height: min(100svh - 52px, 920px);
    scroll-snap-stop: normal;
  }
}

.oleo-section__inner {
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
}

/* Hero v2 — full viewport, aurora + grain, stream + table */
.oleo-section--hero-v2,
.oleo-section--hero {
  position: relative;
  padding-left: 0;
  padding-right: 0;
  padding-top: 0;
  justify-content: flex-start;
}

.oleo-hero-v2 {
  position: relative;
  width: 100%;
  min-height: min(calc(100svh - 52px), 900px);
  height: min(calc(100svh - 52px), 900px);
  overflow: hidden;
  background: #0a0914;
}

.oleo-hero-aurora {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(
    ellipse 95% 75% at 50% 36%,
    rgba(26, 16, 64, 0.92) 0%,
    rgba(26, 16, 64, 0.35) 38%,
    rgba(10, 9, 20, 0.96) 72%,
    #0a0914 100%
  );
}

.oleo-hero-noise-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  mix-blend-mode: overlay;
}

.oleo-hero-filters-svg {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
}

/* Stage: fixed height — input / processor / table are absolutely positioned (not flow-relative). */
.oleo-hero-v2__body {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
  min-height: min(calc(100svh - 52px), 900px);
  padding: 0;
}

/* z-layering: table < processor < input copy (particles SVG is above all) */
.oleo-hero-table-wrap--layer {
  position: absolute;
  top: 60%;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  z-index: 1;
}

.oleo-hero-processor-card--layer {
  position: absolute;
  top: 52%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2;
}

.oleo-hero-input-shell--layer {
  position: absolute;
  top: 12%;
  left: 0;
  right: 0;
  z-index: 3;
  text-align: center;
  padding: 0 1.25rem;
  max-width: min(92vw, 52rem);
  margin: 0 auto;
  box-sizing: border-box;
}

/* Reserved block for 2 lines — single-line copy stays anchored; float/breathe only moves this stack. */
.oleo-hero-input-text-stack {
  position: relative;
  width: 100%;
  margin: 0 auto;
  font-size: clamp(1.75rem, 3.2vw, 3.25rem);
  line-height: 1.35;
  min-height: calc(2 * 1.35 * 1em);
}

/* Crossfade: two layers overlap in the reserved block */
.oleo-hero-input-text--layer {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  width: 100%;
  margin: 0;
}

/* Hero-scoped SVG particle canvas — absolute within .oleo-hero-v2 (no viewport bleed) */
.oleo-hero-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 10;
  overflow: visible;
}

.oleo-hero-v2__body--static {
  justify-content: unset;
  gap: unset;
}

.oleo-hero-v2__body--static .oleo-reduced-hint {
  position: absolute;
  bottom: 1rem;
  left: 0;
  right: 0;
  margin: 0;
  text-align: center;
}

.oleo-hero-input-shell {
  padding: clamp(1.5rem, 8vh, 4rem) 1.25rem 0.5rem;
  text-align: center;
  max-width: min(92vw, 52rem);
  margin: 0 auto;
}

.oleo-hero-input-shell--static {
  padding-top: 0;
  padding-left: 1.25rem;
  padding-right: 1.25rem;
  padding-bottom: 0;
}

.oleo-hero-input-text {
  margin: 0;
  font-size: clamp(1.75rem, 3.2vw, 3.25rem);
  font-weight: 300;
  letter-spacing: 0.02em;
  line-height: 1.35;
  color: #e8e4df;
  opacity: 0.88;
}

.oleo-hero-stream-column {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  min-height: clamp(100px, 18vh, 200px);
  width: 100%;
  padding: 0.25rem 0;
}

.oleo-hero-stream-track {
  position: relative;
  flex: 1 1 auto;
  width: min(32px, 10vw);
  min-height: clamp(80px, 14vh, 180px);
  margin: 0 auto;
}

/* Wobble + bloom live inside this lane (~8–12px visual spread) */
.oleo-hero-particle-wrap {
  position: absolute;
  left: 50%;
  top: 0;
  width: 24px;
  margin-left: -12px;
  pointer-events: none;
}

/* Soft indigo bloom behind the core (size/opacity set inline per particle) */
.oleo-hero-particle-bloom {
  position: absolute;
  left: 50%;
  top: 0;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(
    circle at center,
    rgba(129, 140, 248, 0.55) 0%,
    rgba(99, 102, 241, 0.2) 45%,
    transparent 72%
  );
  z-index: 0;
}

/* Variable size + opacity inline; vertical blur trail reads as comet tail */
.oleo-hero-particle-core {
  position: absolute;
  left: 50%;
  top: 0;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(ellipse at center, #818cf8 0%, rgba(129, 140, 248, 0.45) 45%, transparent 72%);
  filter: url(#oleo-hero-particle-trail);
  pointer-events: none;
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.4);
  z-index: 1;
}

.oleo-hero-processor {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin-top: 2px;
  margin-bottom: 2px;
  flex-shrink: 0;
  background: radial-gradient(circle at 40% 40%, #a5b4fc 0%, #818cf8 45%, rgba(129, 140, 248, 0.25) 70%, transparent 100%);
  box-shadow: 0 0 14px rgba(129, 140, 248, 0.45);
  transform-origin: center center;
}

.oleo-hero-processor--static {
  opacity: 0.9;
}

/* Processor card — spec: small glass panel between input and table */
.oleo-hero-processor-card {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 0.75rem;
  width: min(160px, 42vw);
  height: 56px;
  margin: 0 auto;
  padding: 0 0.85rem;
  flex-shrink: 0;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 0 32px rgba(99, 102, 241, 0.12);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.oleo-hero-processor-card--static {
  opacity: 0.95;
}

.oleo-hero-processor-card--idle {
  opacity: 0.85;
}

.oleo-hero-processor-card--idle .oleo-hero-processor-dots span {
  animation-duration: 2s;
  opacity: 0.45;
}

.oleo-hero-processor-dots {
  display: flex;
  align-items: center;
  gap: 4px;
}

.oleo-hero-processor-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #818cf8;
  animation: oleo-processor-dot-wave 1.2s ease-in-out infinite;
}

.oleo-hero-processor-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.oleo-hero-processor-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

.oleo-hero-processor-dots--frozen span {
  animation: none;
  opacity: 0.55;
}

@keyframes oleo-processor-dot-wave {
  0%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-1px);
  }
}

.oleo-hero-processor-label {
  font-size: 11px;
  font-weight: 300;
  color: rgba(255, 255, 255, 0.4);
  letter-spacing: 0.04em;
  white-space: nowrap;
}

.oleo-hero-stream-placeholder {
  flex: 1;
  min-height: 4rem;
  max-height: 8rem;
}

.oleo-hero-table-wrap {
  width: 91%;
  max-width: 1100px;
  margin: 0.75rem auto 0;
  box-shadow: 0 8px 48px rgba(99, 102, 241, 0.08);
}

.oleo-hero-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
  background: rgba(255, 255, 255, 0.025);
  font-size: 13px;
  border: none;
}

.oleo-hero-table thead th {
  width: 20%;
  padding: 0.65rem 0.75rem;
  text-align: left;
  font-weight: 400;
  font-size: 12px;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.38);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oleo-hero-table thead th:last-child {
  border-right: none;
}

.oleo-hero-table tbody td {
  width: 20%;
  padding: 0.85rem 0.75rem;
  min-height: 62px;
  height: 66px;
  vertical-align: middle;
  color: rgba(255, 255, 255, 0.82);
  font-size: 17px;
  font-weight: 300;
  letter-spacing: 0.02em;
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  border-top: 1px solid rgba(255, 255, 255, 0.05);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oleo-hero-table tbody td:last-child {
  border-right: none;
}

/* Notion-style column headers: type icon + label (label alone updates on scene change) */
.oleo-hero-th__inner {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 100%;
}

.oleo-hero-th__icon {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.38);
}

.oleo-hero-th__svg {
  display: block;
}

.oleo-hero-th__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
}

/* Typed cells — baseline td; number column right-aligns at resolve */
.oleo-hero-table tbody td.oleo-hero-td {
  padding: 0.65rem 0.55rem;
}

.oleo-hero-table tbody td.oleo-hero-td--number {
  text-align: right;
}

.oleo-hero-cell-title {
  display: inline-block;
  max-width: 100%;
  font-size: 17px;
  font-weight: 300;
  color: rgba(255, 255, 255, 0.82);
}

.oleo-hero-pill {
  display: inline-block;
  max-width: 100%;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 17px;
  font-weight: 400;
  line-height: 1.25;
  vertical-align: middle;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.oleo-hero-multi-wrap {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  min-width: 0;
  max-width: 100%;
}

.oleo-hero-multi-wrap .oleo-hero-pill {
  flex-shrink: 0;
}

.oleo-hero-multi-wrap .oleo-hero-pill:last-child {
  flex: 1 1 auto;
  min-width: 0;
}

.oleo-hero-relation {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  min-width: 0;
}

.oleo-hero-relation__icon {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  line-height: 0;
}

.oleo-hero-relation__icon svg,
.oleo-hero-relation__icon-svg {
  display: block;
}

.oleo-hero-relation__text {
  font-size: 17px;
  font-weight: 400;
  color: rgba(255, 255, 255, 0.75);
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oleo-hero-cell-number {
  display: inline-block;
  font-family: "SF Mono", "Fira Code", ui-monospace, monospace;
  font-size: 17px;
  font-weight: 400;
  color: rgba(255, 255, 255, 0.82);
}

.oleo-hero-cell--flash {
  box-shadow: inset 0 0 12px rgba(99, 102, 241, 0.2);
}

.oleo-eyebrow {
  margin: 0 0 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--oleo-muted);
}

.oleo-reduced-hint {
  margin: 0.75rem 0 0;
  font-size: 0.8125rem;
  color: var(--oleo-muted);
}

.oleo-section-title {
  margin: 0 0 0.75rem;
  font-size: clamp(1.5rem, 2.5vw, 2rem);
  letter-spacing: -0.03em;
  color: var(--oleo-text);
}

.oleo-section-sub {
  margin: 0 0 2rem;
  max-width: 42rem;
  font-size: 1rem;
  line-height: 155%;
  color: var(--oleo-muted);
}

/* Triggers split */
.oleo-split {
  display: grid;
  grid-template-columns: 1fr;
  gap: 2.5rem;
  align-items: start;
}

@media (min-width: 880px) {
  .oleo-split {
    grid-template-columns: 1fr 1fr;
    gap: 3rem;
    align-items: center;
  }
}

.oleo-split__col--link {
  position: relative;
  padding-left: 0;
}

@media (min-width: 880px) {
  .oleo-split__col--link {
    padding-left: 1.5rem;
  }

  .oleo-link-beam {
    position: absolute;
    left: 0;
    top: 50%;
    width: 4px;
    height: min(70%, 240px);
    transform: translateY(-50%);
    border-radius: 4px;
    background: linear-gradient(180deg, rgba(99, 102, 241, 0.2), rgba(99, 102, 241, 0.85), rgba(99, 102, 241, 0.2));
    box-shadow: 0 0 24px rgba(99, 102, 241, 0.35);
  }
}

.oleo-mock {
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.04);
  padding: 1rem 1.25rem;
  font-size: 0.875rem;
}

.oleo-mock__title {
  font-weight: 600;
  margin-bottom: 0.75rem;
  color: var(--oleo-text);
}

.oleo-mock__field {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--oleo-muted);
}

.oleo-mock__field strong {
  color: var(--oleo-text);
  font-weight: 500;
}

.oleo-mock__field--active {
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.35);
  padding: 0.5rem 0.75rem;
  margin-top: 0.35rem;
}

/* Pipeline schematic */
.oleo-pipeline-schematic {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 0.25rem 0;
  padding: 1.5rem 0;
}

.oleo-pipeline-node {
  padding: 0.55rem 0.9rem;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--oleo-text);
}

.oleo-pipeline-node--dim {
  opacity: 0.55;
  filter: blur(0.5px);
}

.oleo-pipeline-node--pulse {
  animation: oleo-node-pulse 5s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .oleo-pipeline-node--pulse {
    animation: none;
  }
}

@keyframes oleo-node-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.35);
  }
  50% {
    box-shadow: 0 0 28px 2px rgba(99, 102, 241, 0.2);
  }
}

.oleo-pipeline-connector {
  display: flex;
  align-items: center;
  width: 2rem;
  min-width: 1.5rem;
  flex-shrink: 0;
}

.oleo-pipeline-stream {
  display: block;
  height: 2px;
  width: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.65), rgba(99, 102, 241, 0.1));
  opacity: 0.85;
}

@media (max-width: 640px) {
  .oleo-pipeline-schematic {
    flex-direction: column;
  }

  .oleo-pipeline-connector {
    width: 2px;
    height: 1.25rem;
    min-height: 1rem;
  }

  .oleo-pipeline-stream {
    width: 2px;
    height: 100%;
    background: linear-gradient(180deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.65), rgba(99, 102, 241, 0.1));
  }
}

/* Integrations constellation */
.oleo-constellation {
  position: relative;
  padding: 2rem 0 1rem;
}

.oleo-constellation__glow {
  position: absolute;
  inset: 10% 15%;
  border-radius: 50%;
  background: radial-gradient(ellipse at center, rgba(99, 102, 241, 0.14), transparent 65%);
  pointer-events: none;
  z-index: 0;
}

.oleo-constellation__featured,
.oleo-constellation__support {
  position: relative;
  z-index: 1;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 1rem 1.25rem;
}

.oleo-constellation__support {
  margin-top: 1.25rem;
  opacity: 0.95;
}

.oleo-int-card {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 1rem 1.25rem;
  min-width: 140px;
  box-shadow: 0 8px 32px -8px color-mix(in srgb, var(--oleo-int-glow, #6366f1) 15%, transparent);
  transition: transform 0.35s ease, box-shadow 0.35s ease, border-color 0.35s ease;
}

.oleo-int-card:hover {
  border-color: color-mix(in srgb, var(--oleo-int-glow) 45%, rgba(255, 255, 255, 0.2));
  box-shadow: 0 12px 40px -6px color-mix(in srgb, var(--oleo-int-glow) 22%, transparent);
  transform: translateY(-2px);
}

.oleo-int-card--featured {
  min-width: 180px;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
}

.oleo-int-card--support {
  min-width: 120px;
  min-height: 80px;
  padding: 0.75rem 1rem;
}

.oleo-int-card__logo {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--oleo-int-glow) 35%, rgba(255, 255, 255, 0.08));
}

.oleo-int-card__logo--sm {
  width: 28px;
  height: 28px;
  border-radius: 8px;
}

.oleo-int-card__label {
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--oleo-text);
}

.oleo-int-card__hint {
  font-size: 0.75rem;
  color: var(--oleo-muted);
}

.oleo-int-card--drift {
  animation: oleo-card-drift 6s ease-in-out infinite;
  animation-delay: var(--oleo-drift-phase, 0s);
}

@media (prefers-reduced-motion: reduce) {
  .oleo-int-card--drift {
    animation: none;
  }
}

@keyframes oleo-card-drift {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}

/* Beta CTA */
.oleo-beta-inner {
  text-align: center;
  max-width: 36rem;
}

.oleo-beta-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.oleo-cta-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  padding: 0 1.75rem;
  border-radius: 12px;
  font-weight: 600;
  font-size: 1rem;
  text-decoration: none;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: var(--oleo-text);
  transition: background 0.2s ease, border-color 0.2s ease;
}

.oleo-cta-btn--primary {
  background: rgba(99, 102, 241, 0.22);
  border-color: rgba(99, 102, 241, 0.45);
  color: #f0eeeb;
}

.oleo-cta-btn--primary:hover {
  background: rgba(99, 102, 241, 0.35);
  border-color: rgba(99, 102, 241, 0.65);
}

.oleo-cta-btn:focus-visible {
  outline: 2px solid var(--oleo-accent);
  outline-offset: 3px;
}

.oleo-beta-note {
  margin: 0;
  font-size: 0.875rem;
  color: var(--oleo-muted);
  max-width: 28rem;
}
```
