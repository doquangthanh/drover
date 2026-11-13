// Machines: connection cards + "Add a machine" form (SSH target, install, test).
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, icon, errorToast, toast, setTopExtra } from "../dom.js";

function statusPill(m) {
  if (m.status === "connected") return h("span", { class: "pill ok" }, m.latency_ms != null ? `${m.latency_ms} ms` : "Connected");
  if (m.status === "connecting") return h("span", { class: "pill info" }, "Connecting");
  return h("span", { class: "pill bad" }, m.status === "retrying" ? "Retrying" : "Unreachable");
}

function machineCard(m, actions) {
  const snap = m.snapshot || {};
  const retry = m.retry_at ? Math.max(0, Math.round(m.retry_at - Date.now() / 1000)) : 0;
  const on = m.status === "connected";
  const agents = (snap.panes || []).length;
  const need = (snap.panes || []).filter((p) => p.state === "blocked").length;
  return h("div", { class: "mc" },
    h("div", { class: "top" }, icon("server"), h("b", { class: "grow" }, m.alias), statusPill(m)),
    on ? h("div", { class: "st" }, h("span", {}, `hd ${m.info?.version || "?"}`), h("span", {}, `${(snap.spaces || []).length} spaces`), h("span", {}, `${agents} agents`))
      : h("div", { class: "st" }, retry ? h("span", {}, `retry in ${retry}s`) : null),
    h("div", { class: "meta mono" }, m.target),
    on && need ? h("div", { class: "meta" }, `${need} need${need > 1 ? "" : "s"} you`)
      : !on ? h("div", { class: "meta" }, m.error || "Agents there keep running; you'll see them when it's back.") : null,
    h("div", { class: "row" },
      on ? h("button", { class: "btn", onclick: () => actions.newAgent({ machine: m.alias }) }, "New agent here") : null,
      h("button", { class: "btn danger", onclick: () => conn.rpc("machine.remove", { alias: m.alias }).catch(errorToast) }, "Remove")));
}

function addForm() {
  const alias = h("input", { class: "in", id: "m-a", placeholder: "vps-2" });
  const target = h("input", { class: "in mono", id: "m-h", placeholder: "deploy@vps-2.tail-net" });
  const port = h("input", { class: "in", id: "m-p", value: "22" });
  const key = h("input", { class: "in mono", id: "m-k", placeholder: "Use ssh-agent / default keys" });
  const install = h("input", { type: "checkbox" });
  const log = h("div", { class: "box", hidden: true });
  const params = () => ({ alias: alias.value.trim(), target: target.value.trim(), port: Number(port.value) || 22, key: key.value.trim() });
  const test = async () => {
    log.hidden = false; log.replaceChildren(h("div", { class: "row" }, h("span", { class: "spin" }), "Testing SSH…"));
    try {
      const r = await conn.rpc("machine.test", params());
      log.replaceChildren(...r.steps.map((s) => h("div", {}, "✓ ", s)), ...(r.ok ? [] : [h("div", { class: "errtext" }, r.error)]));
    } catch (e) { log.replaceChildren(h("div", { class: "errtext" }, e.message)); }
  };
  const add = async () => {
    log.hidden = false; log.replaceChildren(h("div", { class: "row" }, h("span", { class: "spin" }),
      install.checked ? "Installing hd and connecting…" : "Adding…"));
    try { await conn.rpc("machine.add", { ...params(), install: install.checked }); toast(`Added ${params().alias}`); alias.value = target.value = ""; log.hidden = true; }
    catch (e) { log.replaceChildren(h("div", { class: "errtext" }, e.message)); }
  };
  const field = (id, label, el, hint) => h("div", {}, h("label", { class: "lab", for: id }, label), el, hint ? h("div", { class: "meta", style: { marginTop: "4px" } }, hint) : null);
  return h("aside", { class: "madd" },
    h("div", { style: { fontWeight: 600, fontSize: "14px" } }, "Add a machine"),
    h("div", { class: "madd-body" },
      field("m-a", "Name", alias), field("m-h", "SSH target", target, "user@host or a Host from ~/.ssh/config"),
      h("div", { class: "row" }, h("div", { style: { width: "90px" } }, field("m-p", "Port", port)), h("div", { class: "grow" }, field("m-k", "Key file", key))),
      h("label", { class: "ck" }, install, "Install hd there if missing (Linux/macOS)"),
      h("div", { class: "meta" }, "Host keys are checked against known_hosts. The daemon there only listens on 127.0.0.1; herd reaches it through the SSH tunnel."),
      log,
      h("span", { class: "grow" }),
      h("div", { class: "mono meta" }, "hd machine add <name> <ssh target>"),
      h("div", { class: "row", style: { justifyContent: "flex-end" } }, h("button", { class: "btn", onclick: test }, "Test only"),
        h("button", { class: "btn pri", onclick: add }, "Add"))));
}

export function renderMachines(root, actions) {
  const machines = store.raw.machines || [];
  const local = h("div", { class: "mc" }, h("div", { class: "top" }, icon("monitor"), h("b", { class: "grow" }, "This computer"),
    h("span", { class: "pill ok" }, "Connected")),
  h("div", { class: "st" }, h("span", {}, `${(store.raw.spaces || []).length} spaces`), h("span", {}, `${(store.raw.panes || []).length} agents`)));
  setTopExtra("machines", { right: h("button", { class: "btn pri", onclick: () => document.getElementById("m-a")?.focus() }, "+ Add machine") });
  root.replaceChildren(h("div", { class: "msplit" },
    h("div", { class: "mgrid" }, local, ...machines.map((m) => machineCard(m, actions)),
      h("p", { class: "meta", style: { gridColumn: "1 / -1", padding: "8px 4px", lineHeight: "1.6", margin: 0 } },
        "Phone: with Tailscale on both devices, run `hd server stop` then `hd server run --listen <tailscale-ip>`, ",
        "and open the link from `hd server url` on the phone. Or SSH-tunnel the port. Keep that link private.")),
    addForm()));
}
