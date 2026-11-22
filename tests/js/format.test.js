import assert from "node:assert/strict";
import { test } from "node:test";

import {
  basename,
  eventMessage,
  formatBytes,
  isActive,
  isTerminal,
  pluralize,
  statusTone,
  wordCount,
} from "../../src/daemon/dashboard/static/js/format.js";

test("isActive / isTerminal classify run statuses", () => {
  assert.equal(isActive("running"), true);
  assert.equal(isActive("executing"), true);
  assert.equal(isActive("done"), false);
  assert.equal(isTerminal("failed"), true);
  assert.equal(isTerminal("cancelled"), true);
  assert.equal(isTerminal("queued"), false);
});

test("statusTone maps statuses to tones", () => {
  assert.equal(statusTone("done"), "success");
  assert.equal(statusTone("failed"), "danger");
  assert.equal(statusTone("cancelling"), "warning");
  assert.equal(statusTone("running"), "active");
  assert.equal(statusTone("unknown"), "idle");
});

test("eventMessage renders per event type", () => {
  assert.equal(eventMessage({ type: "plan", plan: [1, 2, 3] }), "3 steps in plan.");
  assert.equal(eventMessage({ type: "step_done", step: { id: 2, title: "Write" } }), "#2 Write");
  assert.equal(
    eventMessage({ type: "step_failed", step: { id: 1, title: "Run" }, retries: 2 }),
    "#1 Run — attempt 2",
  );
  assert.equal(
    eventMessage({ type: "issues", result: { summary: "gaps", issues: ["a", "b"] } }),
    "gaps a · b",
  );
  assert.equal(eventMessage({ type: "status", message: "Planning" }), "Planning");
});

test("formatBytes scales units", () => {
  assert.equal(formatBytes(512), "512 B");
  assert.equal(formatBytes(2048), "2.0 KB");
  assert.equal(formatBytes(5 * 1024 * 1024), "5.0 MB");
  assert.equal(formatBytes(Number.NaN), "");
});

test("basename strips directories across separators", () => {
  assert.equal(basename("a/b/c.txt"), "c.txt");
  assert.equal(basename("a\\b\\d.py"), "d.py");
  assert.equal(basename(""), "");
});

test("wordCount and pluralize", () => {
  assert.equal(wordCount("  one   two three "), 3);
  assert.equal(wordCount(""), 0);
  assert.equal(pluralize(1, "file"), "1 file");
  assert.equal(pluralize(3, "file"), "3 files");
});
