// Single data-access layer for the dashboard API. Every call resolves to parsed
// JSON or throws an ApiError with a human-readable message.

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function describeError(payload, rawText, status) {
  const detail = payload?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc: ["body", "max_retries"], msg: "..."}]
    return detail
      .map((issue) => {
        const field = (issue.loc ?? []).filter((part) => part !== "body").join(".");
        return field ? `${field}: ${issue.msg}` : issue.msg;
      })
      .join("; ");
  }
  if (rawText) return rawText.slice(0, 240);
  return `Request failed (${status})`;
}

export async function request(path, { method = "GET", body, signal } = {}) {
  const init = { method, headers: { Accept: "application/json" }, signal };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Cannot reach the Daemon backend. Is the dashboard server still running?", 0);
  }

  // Read the body exactly once, then decide how to interpret it.
  const rawText = await response.text();
  let payload = null;
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch {
      payload = null;
    }
  }
  if (!response.ok) throw new ApiError(describeError(payload, rawText, response.status), response.status);
  return payload;
}

function withQuery(path, params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "" && value !== false) query.set(key, String(value));
  }
  const text = query.toString();
  return text ? `${path}?${text}` : path;
}

const runPath = (runId) => `/api/runs/${encodeURIComponent(runId)}`;
const projectPath = (name) => `/api/projects/${encodeURIComponent(name)}`;

export const api = {
  health: () => request("/api/health"),

  listRuns: () => request("/api/runs"),
  startRun: (payload) => request("/api/runs", { method: "POST", body: payload }),
  getRun: (runId, options) => request(runPath(runId), options),
  getRunEvents: (runId, options) => request(`${runPath(runId)}/events`, options),
  cancelRun: (runId) => request(`${runPath(runId)}/cancel`, { method: "POST" }),
  cloneRun: (runId) => request(`${runPath(runId)}/clone`, { method: "POST" }),
  sessionLog: (runId) => request(`${runPath(runId)}/session-log`),

  listProjects: (workspace) => request(withQuery("/api/projects", { workspace_dir: workspace })),
  projectFiles: (name, workspace) => request(withQuery(`${projectPath(name)}/files`, { workspace_dir: workspace })),
  projectFile: (name, path, workspace, full = false) =>
    request(withQuery(`${projectPath(name)}/file`, { path, workspace_dir: workspace, full })),

  listLaunches: () => request("/api/launches"),
  launchProject: (name, workspace) =>
    request(withQuery(`${projectPath(name)}/launch`, { workspace_dir: workspace }), { method: "POST" }),
  stopProject: (name) => request(`${projectPath(name)}/stop`, { method: "POST" }),
  restartProject: (name, workspace) =>
    request(withQuery(`${projectPath(name)}/restart`, { workspace_dir: workspace }), { method: "POST" }),
  launchLog: (name) => request(`${projectPath(name)}/launch/log`),
};
