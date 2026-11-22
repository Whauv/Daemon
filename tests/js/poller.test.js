import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import { createPoller } from "../../src/daemon/dashboard/static/js/poller.js";
import { installDocument } from "./_setup.js";

// Poller uses real setTimeout; keep intervals tiny and wait on observable state
// rather than on fixed delays, so the tests stay fast and non-flaky.
const FAST = { interval: 2, maxInterval: 20 };

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeout = 500) {
  const start = Date.now();
  while (!predicate()) {
    if (Date.now() - start > timeout) throw new Error("waitFor timed out");
    await sleep(2);
  }
}

let doc;

beforeEach(() => {
  doc = installDocument({ hidden: false });
});

afterEach(() => {
  doc.restore();
});

test("runs the task on start and stops when it returns false", async () => {
  let calls = 0;
  const poller = createPoller(
    async () => {
      calls += 1;
      return false;
    },
    FAST,
  );
  poller.start();
  await waitFor(() => poller.running === false);
  assert.equal(calls, 1);
});

test("keeps polling while the task returns true", async () => {
  let calls = 0;
  const poller = createPoller(
    async () => {
      calls += 1;
      return calls < 3;
    },
    FAST,
  );
  poller.start();
  await waitFor(() => poller.running === false);
  assert.equal(calls, 3);
});

test("reports failures and recovery", async () => {
  const failures = [];
  let recovered = false;
  let calls = 0;
  const poller = createPoller(
    async () => {
      calls += 1;
      if (calls <= 2) throw new Error("boom");
      return false; // succeed on the third attempt, then stop
    },
    {
      ...FAST,
      onError: (_error, count) => failures.push(count),
      onRecover: () => {
        recovered = true;
      },
    },
  );
  poller.start();
  await waitFor(() => poller.running === false);
  assert.deepEqual(failures, [1, 2]);
  assert.equal(recovered, true);
});

test("does not poll while the document is hidden", async () => {
  let calls = 0;
  doc.setHidden(true);
  const poller = createPoller(
    async () => {
      calls += 1;
      return true;
    },
    FAST,
  );
  poller.start();
  await sleep(20);
  assert.equal(calls, 0, "hidden tab should not poll");

  doc.setHidden(false);
  doc.fireVisibilityChange();
  await waitFor(() => calls > 0);
  poller.stop();
  assert.ok(calls > 0);
});

test("stop halts further polling", async () => {
  let calls = 0;
  const poller = createPoller(
    async () => {
      calls += 1;
      return true;
    },
    FAST,
  );
  poller.start();
  await waitFor(() => calls >= 1);
  poller.stop();
  const snapshot = calls;
  await sleep(20);
  assert.equal(calls, snapshot);
  assert.equal(poller.running, false);
});
