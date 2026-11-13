// Combined view of local + remote machines, plus UI-only selection state.

export const store = {
  raw: { spaces: [], tabs: [], panes: [], stopped: [], machines: [], policy_pending: [] },
  ui: { view: "workspace", tabId: null, spaceId: null, sidebar: true, prefix: false, findPane: null },
  listeners: new Set(),

  set(raw) {
    this.raw = raw;
    this.fixSelection();
    this.emit();
  },

  upsertPane(pane) {
    const machine = this.machineOf(pane.id);
    const list = machine ? machine.snapshot.panes : this.raw.panes;
    if (!list) return;
    const i = list.findIndex((p) => p.id === pane.id);
    if (i >= 0) list[i] = pane; else list.push(pane);
    this.emit();
  },

  machineOf(id) {
    const alias = String(id || "").includes(":") ? id.split(":")[0] : null;
    return alias ? (this.raw.machines || []).find((m) => m.alias === alias && m.snapshot) : null;
  },

  all(key) {
    const out = [...(this.raw[key] || [])];
    for (const m of this.raw.machines || []) out.push(...((m.snapshot || {})[key] || []));
    return out;
  },
  get spaces() { return this.all("spaces"); },
  get tabs() { return this.all("tabs"); },
  get panes() { return this.all("panes"); },
  get stopped() { return this.all("stopped"); },

  pane(id) { return this.panes.find((p) => p.id === id); },
  tab(id) { return this.tabs.find((t) => t.id === id); },
  space(id) { return this.spaces.find((s) => s.id === id); },
  tabsOf(spaceId) { return this.tabs.filter((t) => t.space_id === spaceId); },
  panesOf(spaceId) { return this.panes.filter((p) => p.space_id === spaceId); },
  machineAlias(obj) { return (obj && obj.machine && obj.machine !== "local") ? obj.machine : null; },

  fixSelection() {
    const ui = this.ui;
    if (!this.tab(ui.tabId)) {
      const sameSpace = this.tabsOf(ui.spaceId)[0];
      ui.tabId = (sameSpace || this.tabs[0] || {}).id || null;
    }
    const tab = this.tab(ui.tabId);
    ui.spaceId = tab ? tab.space_id : (this.space(ui.spaceId) ? ui.spaceId : (this.spaces[0] || {}).id || null);
  },

  counts() {
    const c = { blocked: 0, done: 0, working: 0, idle: 0, exited: 0, unread: 0 };
    for (const p of this.panes) { c[p.state] = (c[p.state] || 0) + 1; if (p.unread) c.unread++; }
    return c;
  },

  emit() { for (const fn of this.listeners) fn(); },
  subscribe(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); },
};
