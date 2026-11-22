// Active and past launches of generated project servers.

import { h, reconcile, renderEmpty, setData, setText } from "../dom.js";
import { pulseBorder } from "../motion.js";
import { formatDateTime } from "../format.js";

function launchState(launch) {
  if (launch.running) return { label: "running", tone: "active" };
  if (launch.status === "stopped") return { label: "stopped", tone: "idle" };
  if (launch.exit_code !== null && launch.exit_code !== undefined) {
    return launch.exit_code === 0
      ? { label: "exited", tone: "idle" }
      : { label: `crashed (${launch.exit_code})`, tone: "danger" };
  }
  return { label: "stopped", tone: "idle" };
}

export function createLaunchesView({ onStop, onRestart, onViewLog }) {
  const list = document.getElementById("launches-list");
  const countBadge = document.getElementById("count-launches");

  function createCard() {
    const title = h("p", { class: "card-title" });
    const badge = h("span", { class: "badge" });
    const sub = h("p", { class: "card-sub" });
    const actions = h("div", { class: "card-actions" });
    const node = h("li", { class: "card" }, h("div", { class: "card-head" }, title, badge), sub, actions);
    node._parts = { title, badge, sub, actions };
    return node;
  }

  function updateCard(node, launch) {
    const parts = node._parts;
    const state = launchState(launch);
    pulseBorder(node, launch.running);
    setText(parts.title, launch.project_name);
    setText(parts.badge, state.label);
    setData(parts.badge, "tone", state.tone);
    setText(parts.sub, `${launch.url} · started ${formatDateTime(launch.started_at)}`);

    const signature = `${launch.running}|${launch.docs_url}|${Boolean(launch.log_path)}`;
    if (parts.actions.dataset.signature === signature) return;
    parts.actions.dataset.signature = signature;
    const name = launch.project_name;
    const buttons = [];
    if (launch.running) {
      buttons.push(
        h("a", {
          class: "btn btn-small",
          href: launch.docs_url,
          target: "_blank",
          rel: "noopener noreferrer",
          text: "Open API docs",
          "aria-label": `Open API docs for ${name} (new tab)`,
        }),
      );
    }
    if (launch.log_path) {
      buttons.push(
        h("button", {
          class: "btn btn-small",
          type: "button",
          text: "View log",
          "aria-label": `View server log for ${name}`,
          onClick: (event) => onViewLog(name, event.currentTarget),
        }),
      );
    }
    buttons.push(
      h("button", {
        class: "btn btn-small",
        type: "button",
        text: launch.running ? "Restart" : "Start again",
        "aria-label": `${launch.running ? "Restart" : "Start again"} ${name}`,
        onClick: (event) => onRestart(name, event.currentTarget),
      }),
    );
    if (launch.running) {
      buttons.push(
        h("button", {
          class: "btn btn-small btn-danger",
          type: "button",
          text: "Stop",
          "aria-label": `Stop ${name}`,
          onClick: (event) => onStop(name, event.currentTarget),
        }),
      );
    }
    parts.actions.replaceChildren(...buttons);
  }

  return {
    render(launches, { error }) {
      if (error) {
        renderEmpty(list, "Launch data could not be loaded.", { tone: "danger" });
        return;
      }
      if (!launches) return;
      const running = launches.filter((launch) => launch.running).length;
      setText(countBadge, running ? String(running) : "");
      if (!launches.length) {
        renderEmpty(list, "Nothing launched yet. Use “Launch app” on a project with a FastAPI entrypoint.");
        return;
      }
      reconcile(list, launches, { key: (launch) => launch.project_name, create: createCard, update: updateCard });
    },
  };
}
