import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError, api, request } from "../../src/daemon/dashboard/static/js/api.js";
import { installFetch } from "./_setup.js";

test("request parses a JSON body on success", async () => {
  const stub = installFetch(() => ({ ok: true, status: 200, text: '{"status":"ok"}' }));
  try {
    assert.deepEqual(await request("/api/health"), { status: "ok" });
  } finally {
    stub.restore();
  }
});

test("request throws ApiError with a string detail message", async () => {
  const stub = installFetch(() => ({ ok: false, status: 400, text: '{"detail":"bad path"}' }));
  try {
    await assert.rejects(request("/api/x"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 400);
      assert.equal(error.message, "bad path");
      return true;
    });
  } finally {
    stub.restore();
  }
});

test("request flattens FastAPI validation error arrays", async () => {
  const detail = JSON.stringify({
    detail: [{ loc: ["body", "max_retries"], msg: "must be <= 10" }],
  });
  const stub = installFetch(() => ({ ok: false, status: 422, text: detail }));
  try {
    await assert.rejects(request("/api/runs", { method: "POST", body: {} }), (error) => {
      assert.equal(error.message, "max_retries: must be <= 10");
      return true;
    });
  } finally {
    stub.restore();
  }
});

test("request reports a friendly message when the network is unreachable", async () => {
  const stub = installFetch(() => {
    throw new Error("connection refused");
  });
  try {
    await assert.rejects(request("/api/health"), (error) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 0);
      assert.match(error.message, /Cannot reach the Daemon backend/);
      return true;
    });
  } finally {
    stub.restore();
  }
});

test("query builder keeps truthy params and drops empty/false ones", async () => {
  const stub = installFetch(() => ({ ok: true, status: 200, text: "[]" }));
  try {
    await api.listProjects("demo");
    assert.equal(stub.calls[0].path, "/api/projects?workspace_dir=demo");

    await api.listProjects("");
    assert.equal(stub.calls[1].path, "/api/projects");

    await api.projectFile("demo", "app.py", "demo", false);
    assert.equal(
      stub.calls[2].path,
      "/api/projects/demo/file?path=app.py&workspace_dir=demo",
    );
  } finally {
    stub.restore();
  }
});

test("POST helpers set the method", async () => {
  const stub = installFetch(() => ({ ok: true, status: 200, text: "{}" }));
  try {
    await api.cancelRun("abc");
    assert.equal(stub.calls[0].path, "/api/runs/abc/cancel");
    assert.equal(stub.calls[0].init.method, "POST");
  } finally {
    stub.restore();
  }
});
