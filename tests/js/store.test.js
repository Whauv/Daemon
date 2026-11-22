import assert from "node:assert/strict";
import { test } from "node:test";

import { createStore, watch } from "../../src/daemon/dashboard/static/js/store.js";

test("set merges object patches and updater functions", () => {
  const store = createStore({ a: 1, b: 2 });
  store.set({ a: 10 });
  assert.deepEqual(store.get(), { a: 10, b: 2 });
  store.set((state) => ({ b: state.b + 1 }));
  assert.deepEqual(store.get(), { a: 10, b: 3 });
});

test("subscribe receives next and previous state and can unsubscribe", () => {
  const store = createStore({ n: 0 });
  const seen = [];
  const unsubscribe = store.subscribe((state, previous) => seen.push([previous.n, state.n]));
  store.set({ n: 1 });
  store.set({ n: 2 });
  unsubscribe();
  store.set({ n: 3 });
  assert.deepEqual(seen, [[0, 1], [1, 2]]);
});

test("watch fires immediately then only on identity change of the selected slice", () => {
  const store = createStore({ list: ["a"], other: 1 });
  const renders = [];
  watch(store, (state) => state.list, (value) => renders.push(value));

  // Initial render.
  assert.equal(renders.length, 1);

  // Changing an unrelated slice does not re-render the watched one.
  store.set({ other: 2 });
  assert.equal(renders.length, 1);

  // Replacing the watched slice (new identity) re-renders.
  store.set({ list: ["a", "b"] });
  assert.equal(renders.length, 2);
  assert.deepEqual(renders.at(-1), ["a", "b"]);
});
