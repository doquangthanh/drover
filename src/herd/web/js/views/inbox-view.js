// Inbox: every agent sorted by who needs you; quick answers without opening the pane.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, stateMark, ago, errorToast } from "../dom.js";

let filter = "all";

function excerpt(pane) {
  return pane.state === "blocked" ? (pane.title ? `${pane.title}` : "Waiting for your answer") : "";
}

function card(pane, actions) {
  const space = store.space(pane.space_id);
  const send = (text) => conn.rpc("pane.write", { pane: pane.id, data: text }).catch(errorToast);
  const where = `${space?.name || ""}${pane.machine && pane.machine !== "local" ? " · " + pane.machine : " · This computer"}`;
  const top = h("div", { class: "top" }, kindIcon(pane.kind), h("span", { style: { fontWeight: 500 } }, pane.name),
    h("span", { class: "meta grow" }, `${where} · ${ago(pane.since || pane.created_at)}`), stateMark(pane),
    pane.unread ? h("span", { class: "dot unread" }) : null);
  if (pane.state !== "blocked" && pane.state !== "done" && pane.state !== "exited") {
    return h("div", { class: "lrow", onclick: () => actions.focusPane(pane.id), style: { cursor: "pointer" } }, ...top.childNodes);
  }
  const body = [top];
  if (pane.state === "blocked") {
    body.push(h("div", { class: "ex" }, excerpt(pane)),
      h("div", { class: "row" },
        h("button", { class: "btn pri", onclick: () => send("1") }, "1 · Yes"),
        h("button", { class: "btn", onclick: () => send("2") }, "2"),
        h("button", { class: "btn", onclick: () => send("3") }, "3 · No…"),
        h("span", { class: "grow" }),
        h("button", { class: "btn", onclick: () => send("\x1b") }, "Send Esc"),
        h("button", { class: "btn", onclick: () => actions.focusPane(pane.id) }, "Open")));
  } else if (pane.state === "exited") {
    body.push(h("div", { class: "row" }, h("span", { class: "meta grow" }, `exit code ${pane.exit_code ?? "?"}`),
      h("button", { class: "btn", onclick: () => conn.rpc("pane.restart", { pane: pane.id }).catch(errorToast) }, "Restart & resume"),
      h("button", { class: "btn", onclick: () => conn.rpc("pane.close", { pane: pane.id }).catch(errorToast) }, "Dismiss")));
  } else {
    body.push(h("div", { class: "row" }, h("span", { class: "grow" }),
      h("button", { class: "btn", onclick: () => conn.rpc("pane.focus", { pane: pane.id }) }, "Mark read"),
      h("button", { class: "btn", onclick: () => actions.focusPane(pane.id) }, "Open")));
  }
  return h("div", { class: "card" + (store.ui.focusedPane === pane.id ? " on" : "") }, ...body);
}

function policyCards(actions) {
  return store.all("policy_pending").map((p) => {
    const target = store.pane(p.target);
    const source = store.pane(p.source);
    const machine = String(p.id).includes(":") ? String(p.id).split(":")[0] : null;
    const decide = (allow) => conn.rpc("policy.decide", machine ? { id: p.id, allow, machine } : { id: p.id, allow })
      .catch(errorToast);
    return h("div", { class: "warnbox" },
      h("b", {}, `${source?.name || p.source} tried to answer “${p.text}” for ${target?.name || p.target}. `),
      "Your policy says agents can't approve permission prompts, so it's waiting for you.",
      h("div", { class: "row", style: { marginTop: "8px" } },
        h("button", { class: "btn pri", onclick: () => decide(true) }, "Allow once"),
        h("button", { class: "btn", onclick: () => decide(false) }, "Deny"),
        h("button", { class: "btn", onclick: () => actions.focusPane(p.target) }, "Open")));
  });
}

export function renderInbox(root, actions) {
  const groups = [["Needs you", ["blocked"]], ["Done", ["done"]], ["Working", ["working"]], ["Idle · Exited", ["idle", "exited"]]];
  const panes = store.panes.filter((p) => filter === "all" || (filter === "blocked" && p.state === "blocked")
    || (filter === "done" && p.state === "done") || (filter === "unread" && p.unread));
  const c = store.counts();
  const seg = (key, label) => h("button", { class: "seg" + (filter === key ? " on" : ""),
    onclick: () => { filter = key; renderInbox(root, actions); } }, label);
  const content = [h("div", { class: "row" }, seg("all", `All ${store.panes.length}`), seg("blocked", `Needs you ${c.blocked}`),
    seg("done", `Done ${c.done}`), seg("unread", `Unread ${c.unread}`), h("span", { class: "grow" }),
    h("button", { class: "btn", onclick: () => Promise.all(store.panes.filter((p) => p.unread)
      .map((p) => conn.rpc("pane.focus", { pane: p.id }))).catch(() => {}) }, "Mark all read")),
  ...policyCards(actions)];
  for (const [label, states] of groups) {
    const items = panes.filter((p) => states.includes(p.state));
    if (!items.length) continue;
    content.push(h("div", { class: "sechead" }, label), ...items.map((p) => card(p, actions)));
  }
  if (!store.panes.length) content.push(h("div", { class: "meta" }, "No agents yet."));
  root.replaceChildren(h("div", { class: "view", style: { maxWidth: "980px" } }, ...content));
}
