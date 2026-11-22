import assert from "node:assert/strict";
import { test } from "node:test";

import { readLeadingInteger, staggerDelay } from "../../src/daemon/dashboard/static/js/motion-helpers.js";

test("readLeadingInteger pulls the first integer from display text", () => {
  assert.equal(readLeadingInteger("3 / 8"), 3);
  assert.equal(readLeadingInteger("12 events"), 12);
  assert.equal(readLeadingInteger("-4 retries"), -4);
  assert.equal(readLeadingInteger(""), 0);
  assert.equal(readLeadingInteger(null), 0);
  assert.equal(readLeadingInteger("no digits"), 0);
});

test("staggerDelay scales by index and caps long lists", () => {
  assert.equal(staggerDelay(0), 0);
  assert.equal(staggerDelay(1), 45);
  assert.equal(staggerDelay(3), 135);
  assert.equal(staggerDelay(50), 10 * 45, "capped at the 10th row");
  assert.equal(staggerDelay(-2), 0, "negative index clamps to 0");
});

test("staggerDelay honours custom step and cap", () => {
  assert.equal(staggerDelay(2, { step: 30, cap: 5 }), 60);
  assert.equal(staggerDelay(20, { step: 30, cap: 5 }), 150);
});
