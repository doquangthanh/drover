// Agent tree: who started whom, plus the messages they exchanged (hd run / wait / send / read).
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, stateMark, ago, errorToast } from "../dom.js";

let selected = null;

function nodes(parent, depth, out) {
  // A helper whose parent pane was closed is shown as a root instead of disappearing.
  const isRoot = (p) => !p.parent || !store.pane(p.parent);
  const kids = store.panes.filter((p) => (parent === null ? isRoot(p) : p.parent === parent));
  kids.forEach((p, i) => {
    const last = i === kids.length - 1;
    out.push({ pane: p, prefix: "   ".repeat(Math.max(0, depth - 1)) + (depth ? (last ? "└ " : "├ ") : "") });
    nodes(p.id, depth + 1, out);
  });
  return out;
}

const VERB = { spawn: "started", wait: "is waiting for", send: "→", read: "read", done: "finished for",
  blocked: "needs an answer — asked", denied: "tried to answer for" };

export async function renderTree(root, actions) {
  const rows = nodes(null, 0, []);
  if (!selected || !store.pane(selected)) selected = rows.find((r) => store.panes.some((p) => p.parent === r.pane.id))?.pane.id
    || rows[0]?.pane.id || null;
  const left = h("div", { class: "panel", style: { width: "420px", flex: "none" } },
    h("div", { class: "ph" }, h("b", {}, "Agents"), h("span", { class: "meta grow" }, "who started whom")),
    h("div", { class: "pb-body" }, ...rows.map(({ pane, prefix }) => h("button", {
      class: "srow" + (pane.id === selected ? " on" : ""), onclick: () => { selected = pane.id; renderTree(root, actions); },
    }, h("span", { class: "tree" }, prefix), kindIcon(pane.kind), h("span", { class: "grow trunc" }, pane.name),
    h("span", { class: "meta" }, pane.machine && pane.machine !== "local" ? pane.machine : ago(pane.created_at)), stateMark(pane))),
    rows.length ? null : h("div", { class: "meta" }, "No agents.")),
    selected ? h("div", { class: "row", style: { padding: "10px", borderTop: "1px solid var(--border)", flexWrap: "wrap" } },
      h("button", { class: "btn", onclick: () => actions.focusPane(selected) }, "Open"),
      h("button", { class: "btn", onclick: async () => {
        const text = window.prompt("Send to agent");
        if (text) conn.rpc("pane.send", { pane: selected, text }).catch(errorToast);
      } }, "Send…"),
      h("button", { class: "btn danger", onclick: () => conn.rpc("pane.close", { pane: selected, subtree: true }).catch(errorToast) },
        "Stop with helpers")) : null);
  const msgs = h("div", { class: "pb-body", style: { padding: "4px 14px" } }, h("div", { class: "meta" }, "Loading…"));
  root.replaceChildren(h("div", { class: "vsplit" }, left, h("div", { class: "panel grow" },
    h("div", { class: "ph" }, h("b", {}, "Messages"), h("span", { class: "meta grow" },
      selected ? `${store.pane(selected)?.name} and its helpers` : "")), msgs)));
  if (!selected) { msgs.replaceChildren(h("div", { class: "meta" }, "Start an agent to see activity.")); return; }
  try {
    const list = await conn.rpc("messages.list", { pane: selected });
    const name = (id) => store.pane(id)?.name || id || "you";
    msgs.replaceChildren(...(list.length ? list.slice().reverse().map((m) => h("div", { class: "msg" },
      h("span", { class: "meta mono" }, new Date(m.at * 1000).toLocaleTimeString().slice(0, 5)),
      h("div", {}, h("b", {}, name(m.source)), ` ${VERB[m.kind] || m.kind} `, h("b", {}, name(m.target)),
        m.text ? h("div", { class: "mono meta", style: { marginTop: "3px", whiteSpace: "pre-wrap" } }, m.text) : null)))
      : [h("div", { class: "meta" }, "No agent-to-agent activity yet. Agents use `hd run`, `hd wait`, `hd send`.")]));
  } catch (e) { msgs.replaceChildren(h("div", { class: "errtext" }, e.message)); }
}
