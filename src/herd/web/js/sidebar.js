// Left sidebar: Spaces grouped by machine (top half), Agents grouped by space (bottom half).
import { store } from "./store.js";
import { h, icon, spaceAvatar, kindIcon, stateMark, ago } from "./dom.js";

const ORDER = { blocked: 0, done: 1, working: 2, idle: 3, exited: 4 };

function spaceIndicator(space) {
  const panes = store.panesOf(space.id);
  if (panes.some((p) => p.state === "blocked")) return h("span", { class: "pill blocked" }, "Needs you");
  if (panes.some((p) => p.state === "working")) return h("span", { class: "spin" });
  if (panes.some((p) => p.state === "done")) return h("span", { class: "dot done", style: { margin: "0 3px" } });
  return null;
}

function machineHeader(label, iconName, status, actions) {
  const dot = status === "connected" || status === "local" ? "ok" : status === "error" ? "bad" : "blocked";
  return h("div", { class: "mach" }, icon(iconName, "i"), h("span", { class: "grow trunc" }, label),
    h("button", { class: "ibtn", style: { width: "20px", height: "20px" }, title: "New space here",
      "aria-label": `New space on ${label}`, onclick: actions.newSpace }, "+"),
    h("span", { class: `dot ${dot}`, title: status }));
}

function spaceRow(space, actions) {
  // The close control is a span, not a button: buttons cannot nest inside the row button.
  const close = h("span", { class: "sclose", role: "button", tabindex: "0", title: "Close space", "aria-label": `Close ${space.name}`,
    onclick: (e) => { e.stopPropagation(); actions.closeSpace(space.id); },
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); actions.closeSpace(space.id); } } }, "×");
  const row = h("button", {
    class: "srow" + (store.ui.spaceId === space.id ? " on" : ""), title: space.cwd,
    onclick: () => actions.selectSpace(space.id),
  }, spaceAvatar(space), h("span", { class: "trunc" }, space.name),
  h("span", { class: "git" }, space.branch || "", space.dirty ? h("span", { class: "gb-dirty", title: `${space.dirty} uncommitted` }, "●") : null),
  spaceIndicator(space), close);
  row.addEventListener("contextmenu", (e) => { e.preventDefault(); actions.closeSpace(space.id); });
  return row;
}

function renderSpaces(actions) {
  const list = h("div", { class: "slist" });
  const local = store.raw.spaces || [];
  list.append(machineHeader("This computer", "monitor", "local", { newSpace: () => actions.newSpace(null) }));
  for (const s of local) list.append(spaceRow(s, actions));
  if (!local.length) list.append(h("div", { class: "empty-hint" }, "Open a folder to start: press + or Ctrl+B S."));
  for (const m of store.raw.machines || []) {
    const label = m.status === "connected" ? m.alias : `${m.alias} · ${m.status}`;
    list.append(machineHeader(label, "server", m.status, { newSpace: () => actions.newSpace(m.alias) }));
    for (const s of (m.snapshot || {}).spaces || []) list.append(spaceRow(s, actions));
  }
  return h("div", { class: "sb-half" },
    h("div", { class: "shead" }, h("span", {}, "Spaces"),
      h("button", { class: "ibtn", "aria-label": "Open a folder as a space", onclick: () => actions.newSpace(null) }, "+")),
    list);
}

function agentRow(pane, actions) {
  const on = store.ui.focusedPane === pane.id;
  return h("button", {
    class: `srow ${pane.state}` + (on ? " on" : ""), title: `${pane.command}\n${pane.cwd}`,
    onclick: () => actions.focusPane(pane.id),
  }, kindIcon(pane.kind), h("span", { class: "nm grow trunc" }, pane.name),
  pane.unread ? h("span", { class: "dot unread", title: "unread" }) : null,
  h("span", { class: "t" }, ago(pane.since || pane.created_at)), stateMark(pane));
}

function renderAgents(actions) {
  const list = h("div", { class: "slist" });
  for (const space of store.spaces) {
    const panes = store.panesOf(space.id).sort((a, b) => (ORDER[a.state] ?? 9) - (ORDER[b.state] ?? 9));
    if (!panes.length) continue;
    list.append(h("div", { class: "grp" }, space.machine && space.machine !== "local"
      ? `${space.name} · ${space.machine}` : space.name));
    for (const p of panes) list.append(agentRow(p, actions));
  }
  if (!store.panes.length) list.append(h("div", { class: "empty-hint" }, "No agents yet. Ctrl+B C starts one."));
  return h("div", { class: "sb-half" },
    h("div", { class: "shead", style: { height: "41px" } }, h("span", {}, "Agents"),
      h("button", { class: "ibtn", title: "Agent tree", "aria-label": "Agent tree", onclick: () => actions.show("tree") },
        icon("layers"))),
    list);
}

export function renderSidebar(root, actions) {
  const c = store.counts();
  const nav = (view, iconName, label, extra) => h("button", {
    class: "srow" + (store.ui.view === view ? " on" : ""), onclick: () => actions.show(view),
  }, icon(iconName), h("span", { class: "grow" }, label), extra || null);
  root.replaceChildren(
    h("div", { class: "brand" },
      h("span", { class: "logo" }, "h"), h("span", { class: "name" }, "herd"),
      h("button", { class: "ibtn", "aria-label": "Jump to a terminal", title: "Jump to a terminal (Ctrl+B /)",
        onclick: actions.search }, icon("search")),
      h("button", { class: "ibtn", "aria-label": "Hide sidebar", title: "Hide sidebar (Ctrl+B b)",
        onclick: actions.toggleSidebar }, icon("sidebar"))),
    renderSpaces(actions),
    renderAgents(actions),
    h("div", { class: "sfoot" },
      nav("inbox", "inbox", "Inbox", c.blocked + c.unread ? h("span", { class: "count" }, String(c.blocked || c.unread)) : null),
      nav("machines", "server", "Machines"),
      nav("settings", "gear", "Settings")),
  );
  root.classList.toggle("collapsed", !store.ui.sidebar);
}
