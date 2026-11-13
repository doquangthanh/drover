// Phone-only additions to the top bar: the terminal header (name, place, tab dots) and the Inbox title area.
// Hidden by CSS on wide screens and in the other phone screens; the desktop top bar markup is left untouched.
import { store } from "./store.js";
import { h, icon } from "./dom.js";

function paneHead(actions) {
  const ui = store.ui;
  const pane = store.pane(ui.focusedPane);
  if (!pane) return null;
  const where = pane.machine && pane.machine !== "local" ? pane.machine : "This computer";
  const tabs = store.tabsOf(ui.spaceId);
  const dots = tabs.length > 1 ? h("div", { class: "m-dots", role: "tablist" }, ...tabs.map((t) => h("button", {
    class: "m-dot" + (t.id === ui.tabId ? " on" : ""), role: "tab", "aria-selected": t.id === ui.tabId ? "true" : "false",
    "aria-label": `Tab ${t.name}`, onclick: () => actions.selectTab(t.id) }, h("span")))) : null;
  return h("div", { class: "m-phead" }, h("div", { class: "m-pt trunc" }, pane.name),
    h("div", { class: "m-ps trunc" }, `${store.space(pane.space_id)?.name || ""} · ${where}`), dots);
}

function inboxHead(actions) {
  return [
    h("div", { class: "m-ihead" }, h("button", { class: "m-ibtn", "aria-label": "Settings", onclick: () => actions.show("settings") }, icon("gear"))),
    h("button", { class: "m-isearch", onclick: () => actions.search() }, icon("search"), "Jump to a terminal…"),
  ];
}

export function decorateTopbar(actions) {
  const bar = document.getElementById("topbar");
  if (!bar) return;
  bar.querySelectorAll(".m-phead, .m-ihead, .m-isearch").forEach((el) => el.remove());
  const ui = store.ui;
  if (ui.view === "workspace") { const head = paneHead(actions); if (head) bar.append(head); }
  else if (ui.view === "inbox") bar.append(...inboxHead(actions));
}
