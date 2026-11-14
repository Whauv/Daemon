// Small motion primitives built on the Web Animations API.
// Every helper is a no-op when the user prefers reduced motion, and none of them
// move focus or change layout semantics — they only animate opacity/transform.

const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
const EASE_OUT = "cubic-bezier(0.2, 0.7, 0.2, 1)";

export function prefersReducedMotion() {
  return reducedMotionQuery.matches;
}

function canAnimate(element) {
  return !prefersReducedMotion() && typeof element?.animate === "function";
}

/** Fade + rise an element into place (list insertions, panels, toasts). */
export function enter(element, { y = 6, duration = 220, delay = 0 } = {}) {
  if (!canAnimate(element)) return;
  element.animate(
    [
      { opacity: 0, transform: `translateY(${y}px)` },
      { opacity: 1, transform: "translateY(0)" },
    ],
    { duration, delay, easing: EASE_OUT, fill: "backwards" },
  );
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
  const animation = element.animate(
    [
      { opacity: 1, transform: "translateY(0)" },
      { opacity: 0, transform: "translateY(-4px)" },
    ],
    { duration, easing: EASE_OUT, fill: "forwards" },
  );
  return animation.finished.then(
    () => element.remove(),
    () => element.remove(),
  );
}

/** Brief accent ring to draw the eye to a value that just changed (e.g. run status). */
export function highlight(element) {
  if (!canAnimate(element)) return;
  element.animate(
    [
      { boxShadow: "0 0 0 0 rgba(191, 255, 0, 0.45)" },
      { boxShadow: "0 0 0 8px rgba(191, 255, 0, 0)" },
    ],
    { duration: 650, easing: EASE_OUT },
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
    if (!body || !canAnimate(body)) return;
    event.preventDefault();
    running?.cancel();

    if (details.open) {
      const height = body.offsetHeight;
      running = body.animate(
        [
          { height: `${height}px`, opacity: 1 },
          { height: "0px", opacity: 0 },
        ],
        { duration: 180, easing: EASE_OUT },
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
        { duration: 220, easing: EASE_OUT },
      );
      running.onfinish = () => {
        running = null;
      };
    }
  });
}
