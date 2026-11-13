// Entry point: wires connection, store, renderers and actions.
import { conn } from "./connection.js";
import { store } from "./store.js";
import { toast } from "./dom.js";
import { registerActions, setPrefix } from "./keys.js";
import { renderSidebar } from "./sidebar.js";
import { renderTopbar, renderWorkspace, renderStatus, refreshPaneHeaders } from "./workspace.js";
import { disposeMissing, focusTerminal } from "./terminals.js";
import { buildActions } from "./actions.js";
import { renderInbox } from "./views/inbox-view.js";
import { renderTree } from "./views/tree-view.js";
import { renderMachines } from "./views/machines-view.js";
import { renderChanges } from "./views/changes-view.js";
import { renderSettings } from "./views/settings-view.js";
import { renderServer, maybeShowRestore } from "./views/server-view.js";

const $ = (id) => document.getElementById(id);
const VIEWS = { inbox: renderInbox, tree: renderTree, machines: renderMachines, changes: renderChanges,
  settings: renderSettings, server: renderServer };
const LIVE_VIEWS = new Set(["inbox"]); // re-render on every state change
let lastMachinesKey = "";

/** Machines view: redraw only when a connection changes, and never while the user is typing in it. */
function machinesChanged() {
  if (store.ui.view !== "machines") return false;
  const key = JSON.stringify((store.raw.machines || []).map((m) => [m.alias, m.status, m.error, m.latency_ms]));
  if (key === lastMachinesKey) return false;
  if (document.activeElement && $("altview").contains(document.activeElement) &&
      /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) return false;
  lastMachinesKey = key;
  return true;
}

let lastWorkspaceKey = "";
let lastView = "";

function workspaceKey() {
  const tab = store.tab(store.ui.tabId);
  if (!tab) return "none";
  const ids = JSON.stringify(tab.layout);
  // Only structure goes in the key; names/states are patched in place by refreshPaneHeaders.
  const panes = store.panes.filter((p) => ids.includes(`"${p.id}"`)).map((p) => p.id);
  return JSON.stringify([tab.id, tab.layout, tab.zoomed, tab.zoomed && tab.focused, store.ui.findPane, panes,
    store.stopped.filter((s) => ids.includes(`"${s.id}"`)).map((s) => s.id)]);
}

// Many events can arrive in one burst (status changes, pane updates): draw at most once per frame.
let frameRequested = false;
export function render() {
  if (frameRequested) return;
  frameRequested = true;
  requestAnimationFrame(() => { frameRequested = false; renderNow(); });
}

function renderNow() {
  const ui = store.ui;
  renderSidebar($("sidebar"), actions);
  renderTopbar($("topbar"), actions);
  renderStatus($("statusbar"));
  const inWorkspace = ui.view === "workspace";
  $("workspace").hidden = !inWorkspace;
  $("altview").hidden = inWorkspace;
  if (inWorkspace) {
    const key = workspaceKey();
    if (key !== lastWorkspaceKey) { lastWorkspaceKey = key; renderWorkspace($("workspace"), actions); }
    else { updateFocusClasses(); refreshPaneHeaders(actions); }
  } else if (ui.view !== lastView || LIVE_VIEWS.has(ui.view) || machinesChanged()) {
    VIEWS[ui.view]?.($("altview"), actions);
  }
  lastView = ui.view;
  document.body.classList.toggle("pane-open", !!ui.mobilePane);
  disposeMissing(new Set(store.panes.map((p) => p.id)));
}

function updateFocusClasses() {
  for (const el of document.querySelectorAll(".pane[data-pane]")) {
    el.classList.toggle("focus", el.dataset.pane === store.ui.focusedPane);
  }
  for (const el of document.querySelectorAll(".slot")) {
    el.classList.toggle("has-focus", !!el.querySelector(`.pane[data-pane="${CSS.escape(store.ui.focusedPane || "")}"]`));
  }
}

const actions = buildActions({ render, forceWorkspace: () => { lastWorkspaceKey = ""; }, refreshView: () => { lastView = ""; } });
registerActions(actions);

function onEvent(name, data) {
  if (name === "state" || name === "resync") {
    store.set(data);
    if (name === "resync") conn.reattachAll();
    setPrefix(data.prefix);
    if (!store.ui.focusedPane) {
      const tab = store.tab(store.ui.tabId);
      store.ui.focusedPane = tab?.focused || null;
    }
    maybeShowRestore(actions);
  } else if (name === "pane") {
    store.upsertPane(data);
  } else if (name === "status") {
    const pane = data.pane;
    const visible = document.hasFocus() && store.ui.focusedPane === pane.id && store.ui.view === "workspace";
    if (!visible && (data.new === "blocked" || data.new === "done" || data.new === "exited")) {
      const title = data.new === "blocked" ? `${pane.name} needs you` : data.new === "done" ? `${pane.name} finished` : `${pane.name} stopped`;
      toast(title, pane.title || pane.command, () => actions.focusPane(pane.id));
    }
  } else if (name === "policy") {
    toast(`An agent tried to answer a prompt`, "Open the Inbox to allow or deny it.", () => actions.show("inbox"));
  }
}

conn.onEvent(onEvent);
conn.onConnection = (up) => { $("conn-banner").hidden = up; render(); };
store.subscribe(render);
conn.connect();
window.addEventListener("focus", () => store.ui.focusedPane && focusTerminal(store.ui.focusedPane));
