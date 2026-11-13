// Every user action (buttons, palette, shortcuts) in one place.
import { conn } from "./connection.js";
import { store } from "./store.js";
import { errorToast } from "./dom.js";
import { focusTerminal, sendToPane, copySelection } from "./terminals.js";
import { promptText, confirmBox } from "./modal.js";
import { openPalette } from "./palette.js";
import { openSearch } from "./search.js";
import { openNewAgent } from "./new-agent.js";
import { chooseFolder } from "./folder-picker.js";
import { openShortcuts, openBroadcast } from "./views/server-view.js";

/** Group pane ids by machine: "vps-1:%3" -> vps-1, "%3" -> null (this computer). */
function byMachine(ids) {
  const groups = new Map();
  for (const id of ids || []) {
    const machine = String(id).includes(":") ? String(id).split(":")[0] : null;
    if (!groups.has(machine)) groups.set(machine, []);
    groups.get(machine).push(id);
  }
  return groups;
}

export function buildActions({ render, forceWorkspace, refreshView }) {
  const ui = store.ui;
  const rpc = (m, p) => conn.rpc(m, p).catch((e) => { errorToast(e); throw e; });
  const focused = (opts) => (opts && opts.paneId) || ui.focusedPane;
  const tabPanes = () => {
    const tab = store.tab(ui.tabId);
    return tab ? JSON.stringify(tab.layout).match(/"pane":"([^"]+)"/g)?.map((s) => s.slice(8, -1)) || [] : [];
  };
  const cycle = (states) => {
    const list = store.panes.filter((p) => states.includes(p.state));
    if (!list.length) return;
    const i = list.findIndex((p) => p.id === ui.focusedPane);
    a.focusPane(list[(i + 1) % list.length].id);
  };
  const split = (direction, opts) => {
    const pane = store.pane(focused(opts));
    if (!pane) return a.newAgent();
    const params = { command: "", cwd: pane.cwd, tab_id: pane.tab_id, split_from: pane.id, direction };
    if (pane.machine && pane.machine !== "local") params.machine = pane.machine;
    rpc("pane.create", params).then((p) => a.focusPane(p.id)).catch(() => {});
  };

  const a = {
    show(view) { ui.view = view; ui.mobilePane = view === "workspace" ? ui.mobilePane : false; refreshView(); render(); },
    selectSpace(spaceId) {
      ui.spaceId = spaceId;
      const tab = store.tabsOf(spaceId)[0];
      ui.tabId = tab ? tab.id : null;
      ui.focusedPane = tab?.focused || null;
      ui.view = "workspace";
      render();
    },
    selectTab(tabId) {
      const tab = store.tab(tabId);
      ui.tabId = tabId; ui.spaceId = tab.space_id; ui.focusedPane = tab.focused; ui.view = "workspace";
      render();
      setTimeout(() => focusTerminal(ui.focusedPane), 30);
    },
    focusPane(paneId, fromClick = false) {
      const pane = store.pane(paneId);
      if (!pane) return;
      const changedTab = ui.tabId !== pane.tab_id;
      ui.focusedPane = paneId; ui.tabId = pane.tab_id; ui.spaceId = pane.space_id; ui.mobilePane = true;
      if (ui.view !== "workspace") { ui.view = "workspace"; forceWorkspace(); }
      if (changedTab) forceWorkspace();
      conn.rpc("pane.focus", { pane: paneId }).catch(() => {});
      render();
      if (!fromClick) setTimeout(() => focusTerminal(paneId), 30);
    },
    mobileBack() { ui.mobilePane = false; render(); },
    toggleSidebar() { ui.sidebar = !ui.sidebar; render(); },
    async newSpace(machine) {
      const path = await chooseFolder(machine || null, "");
      if (!path) return;
      const params = { cwd: path };
      if (machine) params.machine = machine;
      const r = await rpc("space.create", params).catch(() => null);
      if (r) a.focusPane(r.pane.id);
    },
    newAgent(opts = {}) { openNewAgent(a, opts); },
    newAgentWorktree() { openNewAgent(a, { worktree: true }); },
    newTab() {
      const space = store.space(ui.spaceId);
      if (!space) return a.newAgent();
      const params = { command: "", cwd: space.cwd };
      if (space.machine && space.machine !== "local") params.machine = space.machine;
      rpc("pane.create", params).then((p) => a.focusPane(p.id)).catch(() => {});
    },
    splitRight(opts) { split("row", opts); },
    splitDown(opts) { split("col", opts); },
    async closePane(opts) {
      const pane = store.pane(focused(opts));
      if (!pane) return;
      if (pane.state === "working" && !(await confirmBox(`Stop ${pane.name}?`, "It is still working.", "Stop", true))) return;
      rpc("pane.close", { pane: pane.id }).then(() => { ui.focusedPane = null; }).catch(() => {});
    },
    async closeTab(tabId) {
      const tab = store.tab(tabId);
      if (!tab || !(await confirmBox(`Close tab ${tab.name}?`, "Every agent in this tab stops.", "Close", true))) return;
      rpc("tab.close", { tab: tabId }).catch(() => {});
    },
    async renameTab(tabId) {
      const tab = store.tab(tabId);
      const name = await promptText("Rename tab", tab.name);
      if (name) rpc("tab.rename", { tab: tabId, name }).catch(() => {});
    },
    async rename(opts) {
      const pane = store.pane(focused(opts));
      if (!pane) return;
      const name = await promptText("Rename agent", pane.name);
      if (name) rpc("pane.rename", { pane: pane.id, name }).catch(() => {});
    },
    zoom(opts) {
      const tab = store.tab(ui.tabId);
      if (!tab) return;
      if (opts?.paneId) ui.focusedPane = opts.paneId;
      if (ui.focusedPane && tab.focused !== ui.focusedPane) conn.rpc("pane.focus", { pane: ui.focusedPane }).catch(() => {});
      rpc("tab.zoom", { tab: tab.id, zoomed: !tab.zoomed }).catch(() => {});
    },
    find(opts) {
      const id = focused(opts);
      if (opts?.query === undefined && ui.findPane === id) { copySelection(id); ui.findPane = null; }
      else ui.findPane = id;
      forceWorkspace(); render();
    },
    restart(opts) { const id = focused(opts); if (id) rpc("pane.restart", { pane: id }).then((p) => a.focusPane(p.id)).catch(() => {}); },
    sendEsc(opts) { const id = focused(opts); if (id) sendToPane(id, "\x1b"); },
    sendRaw(paneId, data) { sendToPane(paneId, data); },
    nextBlocked() { cycle(["blocked"]); },
    nextDone() { cycle(["done"]); },
    focusPrev() { const ids = tabPanes(); const i = ids.indexOf(ui.focusedPane); if (ids.length) a.focusPane(ids[(i - 1 + ids.length) % ids.length]); },
    focusNext() { const ids = tabPanes(); const i = ids.indexOf(ui.focusedPane); if (ids.length) a.focusPane(ids[(i + 1) % ids.length]); },
    gotoTab({ key }) { const tabs = store.tabsOf(ui.spaceId); const t = tabs[Number(key) - 1]; if (t) a.selectTab(t.id); },
    nextTab() { const tabs = store.tabsOf(ui.spaceId); const i = tabs.findIndex((t) => t.id === ui.tabId); if (tabs.length) a.selectTab(tabs[(i + 1) % tabs.length].id); },
    switchSpace() { const s = store.spaces; const i = s.findIndex((x) => x.id === ui.spaceId); if (s.length) a.selectSpace(s[(i + 1) % s.length].id); },
    palette() { openPalette(a); },
    search() { openSearch(a); },
    help() { openShortcuts(); },
    broadcast() { openBroadcast(); },
    inbox() { a.show("inbox"); }, changes() { a.show("changes"); }, machines() { a.show("machines"); },
    settings() { a.show("settings"); }, server() { a.show("server"); }, tree() { a.show("tree"); },
    testNotify() { rpc("notify.test").catch(() => {}); },
    resume(ids, fresh = false) {
      for (const [machine, panes] of byMachine(ids)) {
        rpc("session.resume", machine ? { panes, fresh, machine } : { panes, fresh }).catch(() => {});
      }
    },
    discard(ids) {
      if (!ids) { rpc("session.discard", {}).catch(() => {}); return; } // restore dialog: this computer
      for (const [machine, panes] of byMachine(ids)) {
        rpc("session.discard", machine ? { panes, machine } : { panes }).catch(() => {});
      }
    },
  };
  return a;
}
