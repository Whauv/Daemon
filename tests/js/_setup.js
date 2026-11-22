// Minimal browser-global shims so the dashboard's near-pure modules (poller, api)
// can be imported and driven under Node's built-in test runner without jsdom.
//
// Each helper installs a stub on `globalThis`, returns a controller to drive it,
// and restores whatever was there before when disposed.

/**
 * Install a fake timer scheduler on `globalThis` (setTimeout/clearTimeout).
 * Returns `{ advance, pending, restore }` so a test can run timers deterministically.
 */
export function installFakeTimers() {
  const originalSet = globalThis.setTimeout;
  const originalClear = globalThis.clearTimeout;
  let now = 0;
  let nextId = 1;
  const timers = new Map();

  globalThis.setTimeout = (fn, delay = 0, ...args) => {
    const id = nextId++;
    timers.set(id, { fn, at: now + delay, args });
    return id;
  };
  globalThis.clearTimeout = (id) => {
    timers.delete(id);
  };

  function advance(ms) {
    const until = now + ms;
    // Fire due timers in time order; a fired timer may schedule more.
    while (true) {
      let due = null;
      for (const [id, timer] of timers) {
        if (timer.at <= until && (due === null || timer.at < due.timer.at)) due = { id, timer };
      }
      if (due === null) break;
      timers.delete(due.id);
      now = due.timer.at;
      due.timer.fn(...due.timer.args);
    }
    now = until;
  }

  return {
    advance,
    get pending() {
      return timers.size;
    },
    restore() {
      globalThis.setTimeout = originalSet;
      globalThis.clearTimeout = originalClear;
    },
  };
}

/**
 * Install a stub `document` exposing `hidden` and `addEventListener`.
 * Returns `{ setHidden, fireVisibilityChange, restore }`.
 */
export function installDocument({ hidden = false } = {}) {
  const original = globalThis.document;
  const listeners = new Map();
  const doc = {
    hidden,
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(handler);
    },
    removeEventListener(type, handler) {
      listeners.get(type)?.delete(handler);
    },
  };
  globalThis.document = doc;

  return {
    setHidden(value) {
      doc.hidden = value;
    },
    fireVisibilityChange() {
      for (const handler of listeners.get("visibilitychange") ?? []) handler();
    },
    restore() {
      globalThis.document = original;
    },
  };
}

/**
 * Install a stub `fetch`. `handler(path, init)` may return a response spec
 * `{ ok, status, text }` or throw to simulate a network failure.
 * Returns `{ calls, restore }`.
 */
export function installFetch(handler) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (path, init) => {
    calls.push({ path, init });
    const spec = await handler(path, init);
    const { ok = true, status = 200, text = "" } = spec ?? {};
    return {
      ok,
      status,
      async text() {
        return text;
      },
    };
  };
  return {
    calls,
    restore() {
      globalThis.fetch = original;
    },
  };
}
