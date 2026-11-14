// Feedback: an aria-live announcer for screen readers plus visual toasts.

import { h } from "../dom.js";
import { enter, exit } from "../motion.js";

const MAX_TOASTS = 3;

export function createFeedback({ region, announcer }) {
  function announce(message) {
    // Clearing first makes repeated identical messages re-announce.
    announcer.textContent = "";
    window.setTimeout(() => {
      announcer.textContent = message;
    }, 30);
  }

  function dismiss(toast) {
    if (toast.dataset.exiting) return;
    window.clearTimeout(Number(toast.dataset.timer));
    exit(toast);
  }

  function toast(message, { tone = "info", timeout, action } = {}) {
    announce(message);
    const close = h("button", { class: "toast-close", type: "button", "aria-label": "Dismiss notification", text: "×" });
    const body = h("p", { class: "toast-text", text: message });
    if (action?.href) {
      body.append(" ", h("a", { href: action.href, target: "_blank", rel: "noopener noreferrer", text: action.label }));
    }
    const element = h("div", { class: "toast", dataset: { tone } }, body, close);
    close.addEventListener("click", () => dismiss(element));

    const live = [...region.children].filter((child) => !child.dataset.exiting);
    if (live.length >= MAX_TOASTS) dismiss(live[0]);
    region.append(element);
    enter(element, { y: 10 });

    const duration = timeout ?? (tone === "danger" ? 9000 : 5000);
    element.dataset.timer = String(window.setTimeout(() => dismiss(element), duration));
    // Keep the toast while the pointer or keyboard focus is on it.
    element.addEventListener("mouseenter", () => window.clearTimeout(Number(element.dataset.timer)));
    element.addEventListener("focusin", () => window.clearTimeout(Number(element.dataset.timer)));
    return element;
  }

  return {
    announce,
    info: (message, options) => toast(message, { ...options, tone: "info" }),
    success: (message, options) => toast(message, { ...options, tone: "success" }),
    error: (error, options) => toast(error?.message ?? String(error), { ...options, tone: "danger" }),
  };
}
