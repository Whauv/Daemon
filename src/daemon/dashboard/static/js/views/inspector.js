// Project inspector: file list plus a read-only viewer that also shows session
// logs and launch logs.

import { h, renderEmpty, setText } from "../dom.js";
import { formatBytes, pluralize } from "../format.js";

export function createInspectorView({ onSelectFile, onLoadFull }) {
  const title = document.getElementById("inspector-title");
  const filesList = document.getElementById("files-list");
  const meta = document.getElementById("file-meta");
  const content = document.getElementById("file-content");
  const loadFull = document.getElementById("load-full-file-button");

  renderEmpty(filesList, "Choose “Inspect files” on a project.");
  loadFull.addEventListener("click", () => onLoadFull(loadFull));

  function markCurrent(path) {
    for (const button of filesList.querySelectorAll(".file-row")) {
      if (button.dataset.path === path) button.setAttribute("aria-current", "true");
      else button.removeAttribute("aria-current");
    }
  }

  function showText(label, text) {
    setText(meta, label);
    content.textContent = text;
    content.scrollTop = 0;
    loadFull.hidden = true;
  }

  return {
    showLoading(projectName) {
      setText(title, projectName);
      renderEmpty(filesList, "Loading files…");
      showText(`Loading ${projectName}…`, "");
    },

    showFiles(projectName, files) {
      setText(title, `${projectName} · ${pluralize(files.length, "file")}`);
      if (!files.length) {
        renderEmpty(filesList, "This project has no files.");
        showText("No files to preview.", "");
        return;
      }
      filesList.setAttribute("aria-busy", "false");
      filesList.replaceChildren(
        ...files.map((file) =>
          h(
            "li",
            null,
            h(
              "button",
              {
                class: "file-row",
                type: "button",
                dataset: { path: file.path },
                title: file.path,
                onClick: () => onSelectFile(file.path),
              },
              h("span", { class: "file-name", text: file.path }),
              h("span", { class: "file-size", text: formatBytes(file.size) }),
            ),
          ),
        ),
      );
    },

    showFilesError(projectName, message) {
      setText(title, projectName);
      renderEmpty(filesList, message, { tone: "danger" });
    },

    showFile(file) {
      markCurrent(file.path);
      const flags = [formatBytes(file.size), file.binary ? "binary" : null, file.truncated ? "preview truncated" : null]
        .filter(Boolean)
        .join(" · ");
      setText(meta, `${file.path} — ${flags}`);
      content.textContent = file.binary ? file.message : file.content;
      if (!file.binary && file.message) content.append(`\n\n— ${file.message}`);
      content.scrollTop = 0;
      loadFull.hidden = !file.truncated;
    },

    showText,
  };
}
