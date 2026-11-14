// Live log: newest-first event list with filtering and copy-to-clipboard.

import { h, reconcile, renderEmpty, setData, setText, uniqueKeys } from "../dom.js";
import { animateDisclosure } from "../motion.js";
import { eventMessage, eventMeta, formatTime } from "../format.js";

export function createEventsView({ feedback }) {
  const list = document.getElementById("events-list");
  const filterInput = document.getElementById("event-filter-input");
  const copyButton = document.getElementById("copy-events-button");
  const countBadge = document.getElementById("count-log");

  let events = [];
  let hasRun = false;

  function createEvent() {
    const type = h("span", { class: "event-type" });
    const time = h("time", { class: "event-time" });
    const message = h("p", { class: "event-message" });
    const raw = h("pre", { class: "output" });
    const details = h("details", { class: "event-details" }, h("summary", { text: "Raw event" }), raw);
    // Serialise lazily: most events are never expanded.
    details.addEventListener("toggle", () => {
      if (details.open && !raw.textContent) raw.textContent = JSON.stringify(node._event, null, 2);
    });
    animateDisclosure(details);
    const node = h("li", { class: "event" }, h("div", { class: "event-head" }, type, time), message, details);
    node._parts = { type, time, message };
    return node;
  }

  function updateEvent(node, { event }) {
    node._event = event;
    const meta = eventMeta(event.type);
    setData(node, "tone", meta.tone);
    setText(node._parts.type, meta.label);
    setText(node._parts.time, formatTime(event.timestamp));
    node._parts.time.setAttribute("datetime", event.timestamp ?? "");
    const message = eventMessage(event);
    setText(node._parts.message, message);
    node._parts.message.hidden = !message;
  }

  function render() {
    setText(countBadge, events.length ? String(events.length) : "");
    if (!hasRun) {
      renderEmpty(list, "Start a run to stream its events here.");
      return;
    }
    const keys = uniqueKeys(events, (event) => `${event.timestamp}|${event.type}`);
    const rows = events.map((event, index) => ({ event, key: keys[index] }));
    const filter = filterInput.value.trim().toLowerCase();
    const visible = (filter
      ? rows.filter(({ event }) => `${eventMeta(event.type).label} ${eventMessage(event)} ${JSON.stringify(event)}`.toLowerCase().includes(filter))
      : rows
    ).reverse();
    if (!visible.length) {
      renderEmpty(list, filter ? "No events match this filter." : "Waiting for the first event…");
      return;
    }
    reconcile(list, visible, { key: (row) => row.key, create: createEvent, update: updateEvent });
  }

  filterInput.addEventListener("input", render);
  copyButton.addEventListener("click", async () => {
    if (!events.length) {
      feedback.info("There are no log lines to copy yet.");
      return;
    }
    try {
      await navigator.clipboard.writeText(events.map((event) => JSON.stringify(event)).join("\n"));
      feedback.success(`Copied ${events.length} log lines.`);
    } catch {
      feedback.error(new Error("Clipboard access was blocked by the browser."));
    }
  });

  return {
    render(nextEvents, { runSelected }) {
      events = nextEvents ?? [];
      hasRun = runSelected;
      render();
    },
  };
}
