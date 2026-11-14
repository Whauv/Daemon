// Generated projects in the selected workspace, with inspect/launch controls.

import { h, reconcile, renderEmpty, setText } from "../dom.js";

export function createProjectsView({ onInspect, onLaunch, onStop }) {
  const list = document.getElementById("projects-list");
  const scope = document.getElementById("projects-scope");
  const countBadge = document.getElementById("count-projects");

  function createCard() {
    const title = h("p", { class: "card-title" });
    const path = h("p", { class: "card-sub" });
    const tags = h("div", { class: "card-tags" });
    const actions = h("div", { class: "card-actions" });
    const node = h("li", { class: "card" }, h("div", null, title, path), tags, actions);
    node._parts = { title, path, tags, actions };
    return node;
  }

  function updateCard(node, { project, launch }) {
    const parts = node._parts;
    setText(parts.title, project.name);
    setText(parts.path, project.path);

    const tagLabels = [
      project.has_app ? "FastAPI entrypoint" : "No app entrypoint",
      project.requirements ? "requirements.txt" : null,
      launch?.running ? `Running · :${launch.port}` : null,
    ].filter(Boolean);
    const tagSignature = tagLabels.join("|");
    if (parts.tags.dataset.signature !== tagSignature) {
      parts.tags.dataset.signature = tagSignature;
      parts.tags.replaceChildren(...tagLabels.map((label) => h("span", { class: "tag", text: label })));
    }

    // Rebuild actions only when the launch state changes, so focus is not lost on every refresh.
    const actionSignature = `${project.has_app}|${launch?.running ? launch.docs_url : ""}`;
    if (parts.actions.dataset.signature === actionSignature) return;
    parts.actions.dataset.signature = actionSignature;
    const inspect = h("button", {
      class: "btn btn-small",
      type: "button",
      text: "Inspect files",
      "aria-label": `Inspect files in ${project.name}`,
      onClick: () => onInspect(project.name),
    });
    const buttons = [inspect];
    if (launch?.running) {
      buttons.push(
        h("a", {
          class: "btn btn-small",
          href: launch.docs_url,
          target: "_blank",
          rel: "noopener noreferrer",
          text: "Open API docs",
          "aria-label": `Open API docs for ${project.name} (new tab)`,
        }),
        h("button", {
          class: "btn btn-small btn-danger",
          type: "button",
          text: "Stop",
          "aria-label": `Stop ${project.name}`,
          onClick: (event) => onStop(project.name, event.currentTarget),
        }),
      );
    } else if (project.has_app) {
      buttons.push(
        h("button", {
          class: "btn btn-small",
          type: "button",
          text: "Launch app",
          "aria-label": `Launch ${project.name}`,
          onClick: (event) => onLaunch(project.name, event.currentTarget),
        }),
      );
    }
    parts.actions.replaceChildren(...buttons);
  }

  return {
    render(projects, { launches, workspace, error }) {
      setText(scope, workspace ? `Workspace: ${workspace}` : "Default workspace");
      if (error) {
        setText(countBadge, "");
        renderEmpty(list, `Projects could not be loaded: ${error}`, { tone: "danger" });
        return;
      }
      if (!projects) return;
      setText(countBadge, projects.length ? String(projects.length) : "");
      if (!projects.length) {
        renderEmpty(list, "No generated projects in this workspace yet.");
        return;
      }
      const byName = new Map((launches ?? []).map((launch) => [launch.project_name, launch]));
      reconcile(
        list,
        projects.map((project) => ({ project, launch: byName.get(project.name) })),
        { key: (row) => row.project.path, create: createCard, update: updateCard },
      );
    },
  };
}
