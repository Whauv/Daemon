// Sanity check that the Node test runner and the shim helpers in _setup.js work.
// Phase 2 adds the real behavioral specs for the dashboard modules.

import assert from "node:assert/strict";
import { test } from "node:test";

import { installDocument, installFakeTimers, installFetch } from "./_setup.js";

test("fake timers fire in time order and support cancellation", () => {
  const timers = installFakeTimers();
  try {
    const order = [];
    globalThis.setTimeout(() => order.push("b"), 20);
    globalThis.setTimeout(() => order.push("a"), 10);
    const cancelled = globalThis.setTimeout(() => order.push("x"), 15);
    globalThis.clearTimeout(cancelled);

    timers.advance(25);

    assert.deepEqual(order, ["a", "b"]);
    assert.equal(timers.pending, 0);
  } finally {
    timers.restore();
  }
});

test("document shim toggles visibility and fires listeners", () => {
  const doc = installDocument({ hidden: false });
  try {
    let fired = 0;
    globalThis.document.addEventListener("visibilitychange", () => {
      fired += 1;
    });
    doc.setHidden(true);
    assert.equal(globalThis.document.hidden, true);
    doc.fireVisibilityChange();
    assert.equal(fired, 1);
  } finally {
    doc.restore();
  }
});

test("fetch shim records calls and returns a readable response", async () => {
  const fetchStub = installFetch(() => ({ ok: true, status: 200, text: '{"ok":true}' }));
  try {
    const response = await globalThis.fetch("/api/health", { method: "GET" });
    assert.equal(response.status, 200);
    assert.equal(await response.text(), '{"ok":true}');
    assert.equal(fetchStub.calls[0].path, "/api/health");
  } finally {
    fetchStub.restore();
  }
});
