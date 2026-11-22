// Flat ESLint config. Pinned in package.json: new ESLint releases can enable
// extra default rules and fail CI with no code change (same reason ruff is pinned).

import js from "@eslint/js";

const browserGlobals = {
  document: "readonly",
  window: "readonly",
  fetch: "readonly",
  Response: "readonly",
  AbortController: "readonly",
  URLSearchParams: "readonly",
  setTimeout: "readonly",
  clearTimeout: "readonly",
  setInterval: "readonly",
  clearInterval: "readonly",
  queueMicrotask: "readonly",
  requestAnimationFrame: "readonly",
  console: "readonly",
  navigator: "readonly",
  ResizeObserver: "readonly",
  Node: "readonly",
  Event: "readonly",
  CustomEvent: "readonly",
};

const nodeGlobals = {
  globalThis: "readonly",
  process: "readonly",
};

export default [
  // Vendored, minified third-party code (anime.js) is not ours to lint.
  { ignores: ["src/daemon/dashboard/static/js/vendor/**"] },
  js.configs.recommended,
  {
    files: ["src/daemon/dashboard/static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: browserGlobals,
    },
  },
  {
    files: ["tests/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      // Tests run under Node but exercise browser modules through the shim.
      globals: { ...nodeGlobals, ...browserGlobals },
    },
  },
];
