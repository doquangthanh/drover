// Inbox side panel (desktop): what a notification looks like and which events notify you (from settings.toml [notify]).
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, errorToast } from "../dom.js";

const label = (v, all = false) => {
  if (!Array.isArray(v) || !v.length) return "Off";
  if (all && v.length >= 3) return "All";
  return v.map((x) => x[0].toUpperCase() + x.slice(1)).join(" · ");
};

function sampleToast(pane, kind) {
  const lead = kind === "done" ? h("span", { class: "dot done" }) : kindIcon(pane.kind);
  return h("div", { class: "toast static" }, h("div", { class: "row" }, lead,
    h("b", { class: "grow" }, kind === "done" ? `${pane.name} finished` : `${pane.name} needs you`), h("span", { class: "dim" }, "×")),
  h("div", { class: "sub" }, pane.title || pane.command));
}

export function inboxSidePanel() {
  const n = store.raw.notify || {};
  const quiet = (n.quiet_hours || "").replace("-", " – ");
  const blocked = store.panes.find((p) => p.state === "blocked");
  const done = store.panes.find((p) => p.state === "done");
  const row = (name, value, dim) => h("div", { class: "nrow" }, h("span", {}, name), h("span", { class: dim ? "dim" : "ac" }, value));
  return h("aside", { class: "inbox-side desk", "aria-label": "Notifications" },
    h("div", { class: "meta" }, "In-app toast"),
    blocked ? sampleToast(blocked, "blocked") : null, done ? sampleToast(done, "done") : null,
    !blocked && !done ? h("div", { class: "meta" }, "Toasts appear here and bottom-right when an agent needs you or finishes.") : null,
    h("div", { class: "meta", style: { marginTop: "6px" } }, "Notify me when"),
    h("div", { class: "nlist" },
      row("An agent needs me", label(n.blocked || ["toast", "desktop", "sound"])),
      row("An agent finishes", label(n.done || ["toast", "desktop"])),
      row("An agent crashes", label(n.exited || ["toast", "desktop"], true)),
      row("Quiet hours", quiet || "Off", !quiet)),
    h("div", { class: "meta" }, "Edit these in Settings ▸ Notifications."),
    h("button", { class: "btn sm", style: { alignSelf: "flex-start" }, onclick: () => conn.rpc("notify.test").catch(errorToast) }, "Send a test notification"));
}
