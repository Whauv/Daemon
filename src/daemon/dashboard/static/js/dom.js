// DOM helpers. All text goes through textContent — never innerHTML — so run
// output, file contents, and task text can never inject markup.

import { enter, exit } from "./motion.js";
import { staggerDelay } from "./motion-helpers.js";

/**
 * Create an element. Props: `class`, `text`, `dataset`, `on<Event>` handlers,
 * DOM properties (booleans such as `disabled`/`hidden`), or attributes (strings).
 */
export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") element.className = value;
    else if (key === "text") element.textContent = value;
    else if (key === "dataset") Object.assign(element.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      element.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (typeof value === "boolean" && key in element) element[key] = value;
    else element.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : String(child));
  }
  return element;
}

/** Update text only when it changed, so screen readers and selection are not disturbed. */
export function setText(element, text) {
  const next = text ?? "";
  if (element.textContent !== next) element.textContent = next;
}

export function setData(element, key, value) {
  const next = value === undefined || value === null ? undefined : String(value);
  if (next === undefined) delete element.dataset[key];
  else if (element.dataset[key] !== next) element.dataset[key] = next;
}

export function clear(element) {
  element.replaceChildren();
}

/** Replace a list's contents with a single empty/error state row. */
export function renderEmpty(container, message, { tone } = {}) {
  container.setAttribute("aria-busy", "false");
  container.replaceChildren(h("li", { class: "empty", dataset: tone ? { tone } : undefined, text: message }));
}

export function renderSkeleton(container, rows = 3) {
  container.setAttribute("aria-busy", "true");
  container.replaceChildren(
    ...Array.from({ length: rows }, () => h("li", { class: "skeleton", "aria-hidden": "true" })),
  );
}

/**
 * Keyed list reconciliation. Existing nodes are reused and updated in place, so
 * open <details>, focus, and scroll position survive every poll. New nodes fade
 * in (only after the first population), removed nodes fade out.
 */
export function reconcile(container, items, { key, create, update, stagger = false }) {
  container.setAttribute("aria-busy", "false");
  const existing = new Map();
  for (const child of [...container.children]) {
    if (child.dataset.key) existing.set(child.dataset.key, child);
    else if (!child.dataset.exiting) child.remove(); // empty states / skeletons
  }
  // Normally the first population appears instantly (no flash on load); with
  // `stagger`, new rows fade-rise in sequence, including that first fill.
  const animateNew = stagger || existing.size > 0;
  const seen = new Set();
  let previous = null;
  let newCount = 0;

  items.forEach((item, index) => {
    const itemKey = String(key(item, index));
    seen.add(itemKey);
    let node = existing.get(itemKey);
    const isNew = !node;
    if (isNew) {
      node = create(item, index);
      node.dataset.key = itemKey;
    }
    update(node, item, index);
    const expected = previous ? previous.nextSibling : container.firstChild;
    if (node !== expected) container.insertBefore(node, expected);
    if (isNew && animateNew) enter(node, stagger ? { delay: staggerDelay(newCount) } : {});
    if (isNew) newCount += 1;
    previous = node;
  });

  for (const [itemKey, node] of existing) {
    if (!seen.has(itemKey)) exit(node);
  }
}

/** Build stable keys for items that may share a natural key (e.g. same timestamp). */
export function uniqueKeys(items, baseKey) {
  const counts = new Map();
  return items.map((item) => {
    const base = baseKey(item);
    const count = counts.get(base) ?? 0;
    counts.set(base, count + 1);
    return count ? `${base}#${count}` : base;
  });
}

/** Toggle a button's busy state with a spinner while an async action runs. */
export async function withBusy(button, busyLabel, action) {
  if (!button) return action();
  const label = button.textContent;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.replaceChildren(h("span", { class: "spinner", "aria-hidden": "true" }), busyLabel);
  try {
    return await action();
  } finally {
    button.removeAttribute("aria-busy");
    button.textContent = label;
    button.disabled = false;
  }
}
