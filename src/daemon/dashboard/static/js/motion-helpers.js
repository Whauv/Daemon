// Pure helpers shared by motion.js and dom.js, deliberately free of browser
// globals (no window/document/anime.js) so they can be unit-tested under Node
// without a DOM. The animation itself lives in motion.js.

/** Read the first integer out of an element's current text (e.g. "3 / 8" -> 3). */
export function readLeadingInteger(text) {
  const match = String(text ?? "").match(/-?\d+/);
  return match ? Number(match[0]) : 0;
}

/** Entrance delay for the Nth freshly inserted row, capped so long lists settle quickly. */
export function staggerDelay(index, { step = 45, cap = 10 } = {}) {
  return Math.min(Math.max(index, 0), cap) * step;
}
