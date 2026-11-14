# dashboard static

Frontend for the Daemon dashboard. Plain HTML, CSS, and native ES modules — no build step or
Node dependency is needed to run it.

- `index.html` — dashboard markup (served at `/dashboard` with a strict CSP: no inline scripts).
- `404.html` — fallback page for unknown non-API routes.
- `css/tokens.css` — shared design tokens (colour, type, spacing, motion), also used by the
  landing page and 404 page.
- `css/dashboard.css` — dashboard layout and components.
- `js/main.js` — entry point: application state, polling, and wiring between data and views.
- `js/api.js` — the only module that talks to the API; throws `ApiError` with readable messages.
- `js/store.js`, `js/poller.js` — tiny observable store and a back-off polling loop.
- `js/dom.js` — element builder (text only, never `innerHTML`) and keyed list reconciliation.
- `js/motion.js` — Web Animations API primitives; all are no-ops under `prefers-reduced-motion`.
- `js/ui/` — feedback (toasts + live-region announcer) and accessible tabs.
- `js/views/` — one module per panel: composer, run, events, history, projects, launches, inspector.

`app.js` is the previous single-file implementation. It is no longer referenced by `index.html`
and can be deleted once its uncommitted changes are no longer needed.
