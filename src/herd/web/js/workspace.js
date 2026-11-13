// Tab bar, split layout with draggable gutters, pane chrome, status bar.
import { store } from "./store.js";
import { conn } from "./connection.js";
import { h, fill, icon, kindIcon, stateMark, shortPath } from "./dom.js";
import { getTerminal, focusTerminal, findInPane, sendToPane } from "./terminals.js";

export function renderTopbar(root, actions) {
  const ui = store.ui;
  if (ui.view !== "workspace") {
    const titles = { inbox: "Inbox", machines: "Machines", settings: "Settings", changes: "Changes",
      tree: "Agent tree", server: "herd-server" };
    root.replaceChildren(
      h("button", { class: "pb", onclick: () => actions.show("workspace"), "aria-label": "Back to terminals" },
        icon("back"), "Terminals"),
      h("span", { class: "title" }, titles[ui.view] || ""), h("span", { class: "grow" }));
    return;
  }
  const tabs = store.tabsOf(ui.spaceId).map((tab) => {
    const focused = store.pane(tab.focused) || store.panes.find((p) => p.tab_id === tab.id);
    return h("div", { class: "tab" + (tab.id === ui.tabId ? " on" : ""), role: "tab", tabindex: "0",
      onclick: () => actions.selectTab(tab.id), ondblclick: () => actions.renameTab(tab.id) },
    focused ? kindIcon(focused.kind) : null, tab.name, focused ? stateMark(focused) : null,
    h("button", { class: "x", "aria-label": `Close tab ${tab.name}`,
      onclick: (e) => { e.stopPropagation(); actions.closeTab(tab.id); } }, "×"));
  });
  fill(root,
    h("button", { class: "pb mobile-back", onclick: actions.mobileBack, "aria-label": "Back" }, icon("back")),
    ...(ui.sidebar ? [] : [h("button", { class: "pb", "aria-label": "Show sidebar", onclick: actions.toggleSidebar },
      icon("sidebar"))]),
    ...tabs,
    h("button", { class: "pb", "aria-label": "New agent", title: "New agent (Ctrl+B c)", onclick: actions.newAgent }, "+"),
    h("span", { class: "grow" }),
    h("button", { class: "pb wide", onclick: actions.splitRight, title: "Split right (Ctrl+B %)" }, icon("split")),
    h("button", { class: "pb wide", onclick: () => actions.show("tree") }, "Agents"),
    h("button", { class: "pb wide", onclick: () => actions.show("changes") }, "Changes"));
}

function paneEl(paneId, actions) {
  const pane = store.pane(paneId);
  const stopped = store.stopped.find((s) => s.id === paneId);
  if (!pane) {
    return h("div", { class: "pane" },
      h("div", { class: "phead" }, stopped ? kindIcon(stopped.kind) : null,
        h("span", { class: "pn" }, stopped ? stopped.name : paneId), h("span", { class: "cwd trunc" }, stopped?.cwd || "")),
      h("div", { class: "stopped" }, "This agent stopped when the computer restarted.",
        h("div", { class: "row" },
          h("button", { class: "btn pri", onclick: () => actions.resume([paneId]) }, "Resume"),
          h("button", { class: "btn", onclick: () => actions.resume([paneId], true) }, "Start fresh"),
          h("button", { class: "btn", onclick: () => actions.discard([paneId]) }, "Close"))));
  }
  const focused = store.ui.focusedPane === paneId;
  const entry = getTerminal(paneId);
  const parts = [paneHeader(pane, actions)];
  if (store.ui.findPane === paneId) parts.push(findBar(paneId, actions));
  parts.push(entry.el);
  parts.push(keybar(paneId));
  return h("div", { class: "pane" + (focused ? " focus" : ""), "data-pane": paneId, onmousedown: () => actions.focusPane(paneId, true) },
    ...parts);
}

function paneHeader(pane, actions) {
  const paneId = pane.id;
  return h("div", { class: "phead" }, kindIcon(pane.kind), h("span", { class: "pn" }, pane.name),
    h("span", { class: "cwd trunc", title: pane.cwd }, shortPath(pane.cwd) + (pane.machine && pane.machine !== "local"
      ? ` · ${pane.machine}` : "")),
    stateMark(pane),
    h("button", { class: "ibtn", title: "Split right", "aria-label": "Split right",
      onclick: (e) => { e.stopPropagation(); actions.splitRight({ paneId }); } }, icon("split")),
    h("button", { class: "ibtn", title: "Zoom", "aria-label": "Zoom pane",
      onclick: (e) => { e.stopPropagation(); actions.zoom({ paneId }); } }, icon("zoom")),
    h("button", { class: "ibtn", title: "Close", "aria-label": "Close pane",
      onclick: (e) => { e.stopPropagation(); actions.closePane({ paneId }); } }, icon("close")));
}

/** Cheap update: refresh pane headers (name, state) without moving terminals. */
export function refreshPaneHeaders(actions) {
  for (const el of document.querySelectorAll(".pane[data-pane]")) {
    const pane = store.pane(el.dataset.pane);
    const head = el.querySelector(":scope > .phead");
    if (!pane || !head) continue;
    const sig = [pane.name, pane.state, pane.cwd, pane.exit_code].join("|");
    if (head.dataset.sig === sig) continue;
    const fresh = paneHeader(pane, actions);
    fresh.dataset.sig = sig;
    head.replaceWith(fresh);
  }
}

function findBar(paneId, actions) {
  const status = h("span", { class: "meta" }, "");
  const input = h("input", { "aria-label": "Find in scrollback", placeholder: "Find in scrollback",
    oninput: () => { const r = findInPane(paneId, input.value); status.textContent = r.total ? `${r.index} of ${r.total}` : "no match"; },
    onkeydown: (e) => {
      if (e.key === "Escape") { actions.find({ paneId }); }
      if (e.key === "Enter") { const r = findInPane(paneId, input.value, true, e.shiftKey ? 1 : -1);
        status.textContent = r.total ? `${r.index} of ${r.total}` : "no match"; }
    } });
  setTimeout(() => input.focus(), 0);
  return h("div", { class: "findbar" }, icon("search"), input, status, h("span", { class: "grow" }),
    h("span", { class: "meta" }, "Enter older · Shift+Enter newer · select text to copy · Esc close"));
}

function keybar(paneId) {
  const keys = [["1", "1"], ["2", "2"], ["3", "3"], ["Esc", "\x1b"], ["Tab", "\t"], ["↑", "\x1b[A"], ["↓", "\x1b[B"],
    ["^C", "\x03"], ["⏎", "\r"]];
  const compose = h("input", { class: "compose", placeholder: "Compose…", "aria-label": "Message to agent",
    onkeydown: (e) => { if (e.key === "Enter") { sendToPane(paneId, compose.value + "\r"); compose.value = ""; } } });
  return h("div", { class: "keybar" }, compose,
    keys.map(([label, data]) => h("button", { onclick: () => sendToPane(paneId, data) }, label)));
}

function nodeEl(node, path, tab, actions) {
  if (node.pane) {
    const has = node.pane === store.ui.focusedPane;
    return h("div", { class: "slot" + (has ? " has-focus" : ""), "data-slot": node.pane, style: { flex: "1 1 0" } }, paneEl(node.pane, actions));
  }
  const a = nodeEl(node.a, path + "a", tab, actions);
  const b = nodeEl(node.b, path + "b", tab, actions);
  a.style.flex = `${node.ratio} 1 0`;
  b.style.flex = `${1 - node.ratio} 1 0`;
  const containsFocus = (n) => n.pane ? n.pane === store.ui.focusedPane : containsFocus(n.a) || containsFocus(n.b);
  if (containsFocus(node.a)) a.classList.add("has-focus");
  if (containsFocus(node.b)) b.classList.add("has-focus");
  const gutter = h("div", { class: "gutter", role: "separator" });
  const box = h("div", { class: `split ${node.split}` }, a, gutter, b);
  gutter.addEventListener("pointerdown", (ev) => {
    gutter.setPointerCapture(ev.pointerId);
    const rect = box.getBoundingClientRect();
    const move = (e) => {
      const r = node.split === "row" ? (e.clientX - rect.left) / rect.width : (e.clientY - rect.top) / rect.height;
      node.ratio = Math.max(0.1, Math.min(0.9, r));
      a.style.flex = `${node.ratio} 1 0`; b.style.flex = `${1 - node.ratio} 1 0`;
    };
    const up = () => {
      gutter.removeEventListener("pointermove", move);
      conn.rpc("tab.set_layout", { tab: tab.id, layout: tab.layout }).catch(() => {});
    };
    gutter.addEventListener("pointermove", move);
    gutter.addEventListener("pointerup", up, { once: true });
  });
  return box;
}

export function renderWorkspace(root, actions) {
  const tab = store.tab(store.ui.tabId);
  const hadFocus = document.activeElement?.closest?.(".xterm") ? store.ui.focusedPane : null;
  if (!tab || !tab.layout) {
    root.replaceChildren(h("div", { class: "welcome" }, h("div", { class: "card" },
      h("h1", {}, "Start an agent"),
      h("p", {}, "Pick a folder and an agent. It keeps running in herd-server even when you close this window."),
      h("div", { class: "row" }, h("button", { class: "btn pri", onclick: actions.newAgent }, "New agent"),
        h("button", { class: "btn", onclick: () => actions.newSpace(null) }, "Open folder")),
      h("p", { class: "meta" }, "Shortcuts: Ctrl+B then ? for the full list."))));
    return;
  }
  const node = tab.zoomed && tab.focused ? { pane: tab.focused } : tab.layout;
  root.replaceChildren(nodeEl(node, "", tab, actions));
  if (hadFocus) focusTerminal(hadFocus);
}

export function renderStatus(root) {
  const c = store.counts();
  const pane = store.pane(store.ui.focusedPane);
  const machines = store.raw.machines || [];
  const up = 1 + machines.filter((m) => m.status === "connected").length;
  fill(root,
    h("span", { class: "row", style: { gap: "6px" } }, h("span", { class: `dot ${conn.connected ? "ok" : "bad"}` }),
      conn.connected ? "herd-server up" : "reconnecting…"),
    h("span", {}, `${up} of ${1 + machines.length} machines · ${store.spaces.length} spaces · ${store.panes.length} agents`),
    c.blocked ? h("span", { class: "blocked" }, `${c.blocked} need you`) : null,
    pane ? h("span", { class: "trunc" }, shortPath(pane.cwd)) : null,
    h("span", { class: "grow" }),
    store.ui.prefix ? h("span", { class: "prefix-on" }, "Ctrl+B — waiting for a key") : h("span", {},
      h("span", { class: "k" }, "Ctrl B"), " ", h("span", { class: "k" }, "?"), " shortcuts"));
}
