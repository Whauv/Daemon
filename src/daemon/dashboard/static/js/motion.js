// Motion primitives for the dashboard, powered by self-hosted anime.js v4
// (served from /static, so CSP `script-src 'self'` is satisfied; animations run
// through CSSOM, which `style-src` does not restrict).
//
// Every helper is a no-op under prefers-reduced-motion and only animates
// opacity / transform / a box-shadow accent — none move focus or change layout
// semantics. Transient fades and the animated-number/stagger primitives run on
// anime.js; the box-shadow ring and the <details> height tween stay on the Web
// Animations API, where their property interpolation is simplest and proven.

import { animate, cubicBezier } from "./vendor/animejs/anime.esm.min.js";
import { readLeadingInteger } from "./motion-helpers.js";

const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
const EASE_OUT = cubicBezier(0.2, 0.7, 0.2, 1);

export function prefersReducedMotion() {
  return reducedMotionQuery.matches;
}

function canAnimate(element) {
  return !prefersReducedMotion() && element != null;
}

function canWaapi(element) {
  return !prefersReducedMotion() && typeof element?.animate === "function";
}

/** Fade + rise an element into place (list insertions, panels, toasts). */
export function enter(element, { y = 6, duration = 220, delay = 0 } = {}) {
  if (!canAnimate(element)) return;
  animate(element, {
    opacity: [0, 1],
    translateY: [y, 0],
    duration,
    delay,
    ease: EASE_OUT,
    onComplete: () => {
      // Return to the CSS resting state so no inline opacity/transform lingers.
      element.style.opacity = "";
      element.style.transform = "";
    },
  });
}

/**
 * Fade an element out, then remove it. The node is un-keyed immediately so list
 * reconciliation treats it as gone even while it animates.
 */
export function exit(element, { duration = 160 } = {}) {
  delete element.dataset.key;
  element.dataset.exiting = "true";
  element.setAttribute("aria-hidden", "true");
  if (!canAnimate(element)) {
    element.remove();
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    animate(element, {
      opacity: [1, 0],
      translateY: [0, -4],
      duration,
      ease: EASE_OUT,
      onComplete: resolve,
    });
  }).then(() => element.remove());
}

/**
 * Tween a numeric readout from its current value to `to` (Motion-Primitives
 * "Animated Number"). `format` turns the rounded number into the displayed text,
 * so callers keep control of surrounding copy (e.g. `3 / 8`). Reduced motion or a
 * no-change update writes the final value immediately.
 */
export function animateNumber(element, to, { duration = 420, format = (value) => String(value) } = {}) {
  if (element == null) return;
  const target = Number.isFinite(Number(to)) ? Math.round(Number(to)) : 0;
  const from = readLeadingInteger(element.textContent);
  if (!canAnimate(element) || from === target) {
    element.textContent = format(target);
    return;
  }
  const state = { value: from };
  animate(state, {
    value: target,
    duration,
    ease: EASE_OUT,
    onUpdate: () => {
      element.textContent = format(Math.round(state.value));
    },
    onComplete: () => {
      element.textContent = format(target);
    },
  });
}

/** Toggle a slow accent-border pulse on a live surface (a restrained "border beam"). */
export function pulseBorder(element, active = true) {
  if (element == null) return;
  // The pulse itself is a CSS keyframe on `.is-live` (auto-zeroed under the
  // reduced-motion media query in tokens.css), so it stays cheap and declarative.
  element.classList.toggle("is-live", Boolean(active));
}

/** Brief accent ring to draw the eye to a value that just changed (e.g. run status). */
export function highlight(element) {
  if (!canWaapi(element)) return;
  element.animate(
    [
      { boxShadow: "0 0 0 0 rgba(191, 255, 0, 0.45)" },
      { boxShadow: "0 0 0 8px rgba(191, 255, 0, 0)" },
    ],
    { duration: 650, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" },
  );
}

/**
 * Smoothly expand/collapse a <details> element. Native keyboard behaviour is kept
 * because we only intercept the summary's click (which Enter/Space also fire).
 */
export function animateDisclosure(details) {
  const summary = details.querySelector(":scope > summary");
  if (!summary || details.dataset.motionBound) return;
  details.dataset.motionBound = "true";
  let running = null;

  summary.addEventListener("click", (event) => {
    const body = details.querySelector(":scope > :not(summary)");
    if (!body || !canWaapi(body)) return;
    event.preventDefault();
    running?.cancel();

    if (details.open) {
      const height = body.offsetHeight;
      running = body.animate(
        [
          { height: `${height}px`, opacity: 1 },
          { height: "0px", opacity: 0 },
        ],
        { duration: 180, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" },
      );
      running.onfinish = () => {
        details.open = false;
        running = null;
      };
    } else {
      details.open = true;
      const height = body.offsetHeight;
      running = body.animate(
        [
          { height: "0px", opacity: 0 },
          { height: `${height}px`, opacity: 1 },
        ],
        { duration: 220, easing: "cubic-bezier(0.2, 0.7, 0.2, 1)" },
      );
      running.onfinish = () => {
        running = null;
      };
    }
  });
}
