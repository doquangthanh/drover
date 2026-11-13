// Agent tree: who started whom, plus the messages they exchanged (hd run / wait / send / read).
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, stateMark, ago, errorToast, setTopExtra } from "../dom.js";

let selected = null;
let tab = "messages";

function nodes(parent, indent, out) {
  // A helper whose parent pane was closed is shown as a root instead of disappearing.
  const isRoot = (p) => !p.parent || !store.pane(p.parent);
  const kids = store.panes.filter((p) => (parent === null ? isRoot(p) : p.parent === parent));
  kids.forEach((p, i) => {
    const last = i === kids.length - 1;
    out.push({ pane: p, prefix: indent + (last ? "└ " : "├ ") });
    nodes(p.id, indent + (last ? "   " : "│  "), out);
  });
  return out;
}

const VERB = { spawn: "started", wait: "is waiting for", send: "→", read: "read", done: "finished for",
  blocked: "needs an answer — asked", denied: "tried to answer for" };

export async function renderTree(root, actions) {
  const rows = nodes(null, "", []);
  const orch = store.raw.orchestration || {};
  setTopExtra("tree", { right: h("span", { class: "meta" }, orch.max_panes ? `${rows.length} of ${orch.max_panes} agents · depth limit ${orch.max_depth}` : `${rows.length} agents`) });
  if (!selected || !store.pane(selected)) selected = rows.find((r) => store.panes.some((p) => p.parent === r.pane.id))?.pane.id
    || rows[0]?.pane.id || null;
  const roots = rows.filter((r) => !r.prefix.startsWith(" ") && r.prefix.length === 2).length;
  const left = h("div", { class: "panel tpanel", style: { width: "420px", flex: "none" } },
    h("div", { class: "pb-body", style: { padding: "10px" } },
      h("div", { class: "node" }, h("span", { class: "you" }, "you"), h("span", { class: "meta" }, `started ${roots} agent${roots === 1 ? "" : "s"}`)),
      ...rows.map(({ pane, prefix }) => h("button", {
        class: "node" + (pane.id === selected ? " on" : ""), onclick: () => { selected = pane.id; renderTree(root, actions); },
      }, h("span", { class: "tree" }, prefix), kindIcon(pane.kind), h("span", { class: "grow trunc" }, pane.name),
      h("span", { class: "meta" }, pane.state === "idle" && pane.parent ? "waits" : pane.machine && pane.machine !== "local" ? pane.machine : ago(pane.created_at)),
      stateMark(pane))),
      rows.length ? null : h("div", { class: "meta" }, "No agents.")),
    selected ? h("div", { class: "row tbtn" },
      h("button", { class: "btn", onclick: () => actions.focusPane(selected) }, "Open"),
      h("button", { class: "btn", onclick: async () => {
        const text = window.prompt("Send to agent");
        if (text) conn.rpc("pane.send", { pane: selected, text }).catch(errorToast);
      } }, "Send…"),
      h("button", { class: "btn danger", onclick: () => conn.rpc("pane.close", { pane: selected, subtree: true }).catch(errorToast) },
        "Stop subtree")) : null);
  const msgs = h("div", { class: "pb-body", style: { padding: "4px 14px" } }, h("div", { class: "meta" }, "Loading…"));
  const seg = (id, text) => h("button", { class: "seg" + (tab === id ? " on" : ""), onclick: () => { tab = id; renderTree(root, actions); } }, text);
  root.replaceChildren(h("div", { class: "vsplit" }, left, h("div", { class: "panel grow" },
    h("div", { class: "ph s38", style: { gap: "4px" } }, seg("messages", "Messages"), seg("policy", "Policy"), h("span", { class: "grow" }),
      h("span", { class: "meta" }, selected ? `${store.pane(selected)?.name} and its helpers` : "")), msgs)));
  if (tab === "policy") {
    const o = store.raw.orchestration || {};
    msgs.replaceChildren(h("div", { class: "kv", style: { padding: "10px 0" } },
      h("span", {}, "Agents may answer prompts"), h("span", { class: "mono" }, String(o.agents_may_answer_permission_prompts ?? "ask-user")),
      h("span", {}, "Max agents"), h("span", { class: "mono" }, String(o.max_panes ?? "?")),
      h("span", {}, "Max depth"), h("span", { class: "mono" }, String(o.max_depth ?? "?")),
      h("span", {}, "Stop helpers with parent"), h("span", { class: "mono" }, String(!!o.kill_children_on_parent_exit))),
    h("div", { class: "meta" }, "Edit these under [orchestration] in settings.toml."));
    return;
  }
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
