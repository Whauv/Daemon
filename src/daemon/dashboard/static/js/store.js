// Minimal observable store. Views subscribe and re-render only the slices whose
// identity changed (`state.x !== previous.x`).

export function createStore(initialState) {
  let state = { ...initialState };
  const listeners = new Set();

  return {
    get: () => state,
    set(patch) {
      const previous = state;
      const next = typeof patch === "function" ? patch(state) : patch;
      state = { ...state, ...next };
      for (const listener of listeners) listener(state, previous);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** Run `render(value, state)` whenever `select(state)` changes identity. */
export function watch(store, select, render) {
  render(select(store.get()), store.get());
  return store.subscribe((state, previous) => {
    const value = select(state);
    if (value !== select(previous)) render(value, state);
  });
}
