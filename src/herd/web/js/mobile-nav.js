// Phone navigation: bottom tab bar, "new agent" button and a More sheet. All of it is hidden by CSS on wide screens.
// body[data-m] is "home" (agent list), "pane" (one terminal, full screen) or "view" (Inbox, Files, Changes, ...).
import { store } from "./store.js";
import { h, icon } from "./dom.js";
import { openModal, closeModal } from "./modal.js";
import { decorateTopbar } from "./mobile-topbar.js";
import { watchKeybars } from "./mobile-dictate.js";

const TABS = [
  ["home", "layers", "Agents"], ["inbox", "inbox", "Inbox"], ["files", "folder", "Files"], ["changes", "branch", "Changes"],
  ["more", "more", "More"],
];
const MORE = [
  ["tree", "tree", "Agent tree"], ["machines", "server", "Machines"], ["settings", "gear", "Settings"],
  ["server", "server", "herd-server"], ["search", "search", "Jump to a terminal"], ["palette", "keyboard", "Command palette"],
  ["help", "keyboard", "Keyboard shortcuts"],
];
const IN_MORE = new Set(["tree", "machines", "settings", "server"]);

let nav = null;
let fab = null;

export function mobileMode() {
  const ui = store.ui;
  return ui.view === "workspace" ? (ui.mobilePane ? "pane" : "home") : "view";
}

function openMore(actions) {
  const rows = MORE.map(([action, ic, label]) => h("button", { class: "sheet-row", onclick: () => {
    closeModal();
    setTimeout(() => (["tree", "machines", "settings", "server"].includes(action) ? actions.show(action) : actions[action]?.({})), 0);
  } }, icon(ic), h("span", { class: "grow" }, label)));
  openModal({ title: "More", size: "sheet", body: h("div", { class: "sheet-list" }, ...rows) });
}

function build(actions) {
  nav = h("nav", { id: "bottomnav", "aria-label": "Main" });
  nav.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-tab]");
    if (!btn) return;
    const tab = btn.dataset.tab;
    if (tab === "home") { actions.show("workspace"); store.ui.mobilePane = false; actions.mobileBack(); }
    else if (tab === "more") openMore(actions);
    else actions.show(tab);
  });
  fab = h("button", { id: "fab", "aria-label": "New agent", onclick: () => actions.newAgent() }, icon("plus"), "New agent");
  document.body.append(nav, fab);
  watchKeybars();
  // The on-screen keyboard shrinks the visual viewport: size the app to it so the key bar stays above the keyboard.
  const vv = window.visualViewport;
  if (vv) {
    const fit = () => document.documentElement.style.setProperty("--vvh", `${vv.height}px`);
    vv.addEventListener("resize", fit);
    fit();
  }
}

export function renderMobileNav(actions) {
  if (!nav) build(actions);
  const mode = mobileMode();
  document.body.dataset.m = mode;
  document.body.dataset.view = store.ui.view;
  decorateTopbar(actions);
  const active = mode === "home" ? "home" : IN_MORE.has(store.ui.view) ? "more" : store.ui.view;
  const c = store.counts();
  const badge = c.blocked + c.unread;
  nav.replaceChildren(...TABS.map(([id, ic, label]) => h("button", { "data-tab": id, class: "mt" + (id === active ? " on" : ""),
    "aria-label": label, "aria-current": id === active ? "page" : null },
  h("span", { class: "mt-ic" }, icon(ic), id === "inbox" && badge ? h("span", { class: "count" }, String(badge)) : null),
  h("span", {}, label))));
}
