// Top bar for the full-page views (Inbox, Machines, ...): title + hint on the left, per-view actions on the right.
import { store } from "./store.js";
import { h, fill, icon, topExtra } from "./dom.js";

const TITLES = {
  inbox: ["Inbox"], machines: ["Machines", "reached over SSH · daemons never listen on the network"],
  settings: ["Settings"], tree: ["Agent tree", "who started whom · Ctrl B o"], server: ["herd-server"],
  files: ["Files"], changes: [null, "worktrees"],
};

export function viewBar(root, actions) {
  const ui = store.ui;
  const [title, hint] = TITLES[ui.view] || [""];
  const extra = topExtra.view === ui.view ? topExtra : {};
  const space = store.space(ui.spaceId);
  const back = h("button", { class: "pb" + (ui.view === "files" ? "" : " mobile-only"), onclick: () => actions.show("workspace"),
    "aria-label": "Back to terminals" }, icon("back"), "Terminals");
  const tabsToggle = ui.view === "changes" ? [h("span", { class: "grow" }),
    h("div", { class: "desk row", style: { gap: "2px" } }, ...[["files", "Files"], ["changes", "Changes"]].map(([v, label]) =>
      h("button", { class: "pb" + (ui.view === v ? " on" : ""), onclick: () => actions.show(v) }, label)))] : null;
  root.classList.add("vbar");
  fill(root, back, h("span", { class: "title" }, title ?? (space?.name || "")),
    hint ? h("span", { class: "meta desk" }, hint) : null,
    h("span", { class: "desk row" }, extra.meta),
    tabsToggle || [h("span", { class: "grow" }), ui.view === "files" ? h("span", { class: "meta desk" }, "Ctrl B f · refreshes every 3 s while agents edit") : null],
    h("span", { class: "desk row" }, extra.right));
}
