// Machines: connection cards + "Add a machine" form (SSH target, install, test).
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, icon, errorToast, toast } from "../dom.js";

function statusPill(m) {
  if (m.status === "connected") return h("span", { class: "pill ok" }, m.latency_ms != null ? `${m.latency_ms} ms` : "Connected");
  if (m.status === "connecting") return h("span", { class: "pill info" }, "Connecting");
  return h("span", { class: "pill bad" }, m.status === "retrying" ? "Retrying" : "Unreachable");
}

function machineCard(m, actions) {
  const snap = m.snapshot || {};
  const retry = m.retry_at ? Math.max(0, Math.round(m.retry_at - Date.now() / 1000)) : 0;
  return h("div", { class: "card" },
    h("div", { class: "top" }, icon("server"), h("b", { class: "grow" }, m.alias), statusPill(m)),
    h("div", { class: "meta mono" }, m.target),
    m.status === "connected"
      ? h("div", { class: "meta" }, `${(snap.spaces || []).length} spaces · ${(snap.panes || []).length} agents · hd ${m.info?.version || "?"}`)
      : h("div", { class: "meta" }, m.error || "", retry ? ` · retry in ${retry}s` : ""),
    h("div", { class: "row" },
      m.status === "connected" ? h("button", { class: "btn", onclick: () => actions.newAgent({ machine: m.alias }) }, "New agent here") : null,
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
  return h("div", { class: "panel", style: { width: "380px", flex: "none" } },
    h("div", { class: "ph" }, h("b", {}, "Add a machine")),
    h("div", { class: "pb-body", style: { display: "flex", flexDirection: "column", gap: "12px", padding: "14px" } },
      field("m-a", "Name", alias), field("m-h", "SSH target", target, "user@host or a Host from ~/.ssh/config"),
      h("div", { class: "row" }, h("div", { style: { width: "90px" } }, field("m-p", "Port", port)), h("div", { class: "grow" }, field("m-k", "Key file", key))),
      h("label", { class: "ck" }, install, "Install hd there if missing (Linux/macOS)"),
      h("div", { class: "meta" }, "Host keys are checked against known_hosts. The daemon there only listens on 127.0.0.1; herd reaches it through the SSH tunnel."),
      log,
      h("div", { class: "row" }, h("span", { class: "grow" }), h("button", { class: "btn", onclick: test }, "Test only"),
        h("button", { class: "btn pri", onclick: add }, "Add"))));
}

export function renderMachines(root, actions) {
  const machines = store.raw.machines || [];
  const local = h("div", { class: "card" }, h("div", { class: "top" }, icon("monitor"), h("b", { class: "grow" }, "This computer"),
    h("span", { class: "pill ok" }, "Connected")),
  h("div", { class: "meta" }, `${(store.raw.spaces || []).length} spaces · ${(store.raw.panes || []).length} agents`));
  root.replaceChildren(h("div", { class: "vsplit" },
    h("div", { class: "grow", style: { overflow: "auto", padding: "6px" } },
      h("div", { class: "grid2" }, local, ...machines.map((m) => machineCard(m, actions))),
      h("p", { class: "meta", style: { padding: "8px 4px", lineHeight: "1.6" } },
        "Phone: with Tailscale on both devices, run `hd server stop` then `hd server run --listen <tailscale-ip>`, ",
        "and open the link from `hd server url` on the phone. Or SSH-tunnel the port. Keep that link private.")),
    addForm()));
}
