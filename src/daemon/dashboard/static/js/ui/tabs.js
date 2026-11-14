// Accessible tabs (WAI-ARIA tabs pattern, automatic activation) with an
// animated selection indicator.

import { enter } from "../motion.js";

export function createTabs(tablist, { onChange } = {}) {
  const tabs = [...tablist.querySelectorAll('[role="tab"]')];
  const indicator = document.createElement("span");
  indicator.className = "tab-indicator";
  indicator.setAttribute("aria-hidden", "true");
  tablist.append(indicator);

  const panelFor = (tab) => document.getElementById(tab.getAttribute("aria-controls"));
  let current = tabs.find((tab) => tab.getAttribute("aria-selected") === "true") ?? tabs[0];

  function moveIndicator() {
    indicator.style.transform = `translateX(${current.offsetLeft}px) scaleX(${current.offsetWidth})`;
  }

  function select(tab, { focus = false } = {}) {
    if (!tab) return;
    if (tab !== current) {
      for (const other of tabs) {
        const selected = other === tab;
        other.setAttribute("aria-selected", String(selected));
        other.tabIndex = selected ? 0 : -1;
        panelFor(other).hidden = !selected;
      }
      current = tab;
      enter(panelFor(tab), { y: 4, duration: 180 });
      onChange?.(tab.id);
    }
    if (focus) tab.focus();
    moveIndicator();
  }

  tablist.addEventListener("click", (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab) select(tab);
  });

  tablist.addEventListener("keydown", (event) => {
    const index = tabs.indexOf(current);
    const targets = {
      ArrowRight: tabs[(index + 1) % tabs.length],
      ArrowLeft: tabs[(index - 1 + tabs.length) % tabs.length],
      Home: tabs[0],
      End: tabs[tabs.length - 1],
    };
    const target = targets[event.key];
    if (!target) return;
    event.preventDefault();
    select(target, { focus: true });
  });

  new ResizeObserver(moveIndicator).observe(tablist);
  moveIndicator();

  return {
    select: (id, options) => select(tabs.find((tab) => tab.id === id), options),
    get current() {
      return current.id;
    },
  };
}
