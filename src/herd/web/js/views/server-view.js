// herd-server status + "Pick up where you left off?" restore dialog.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, errorToast, setTopExtra } from "../dom.js";
import { openModal, closeModal } from "../modal.js";

export async function renderServer(root) {
  let info;
  try { info = await conn.rpc("server.info"); } catch (e) { root.replaceChildren(h("div", { class: "view errtext" }, e.message)); return; }
  const up = Math.floor(info.uptime);
  const parts = [[Math.floor(up / 86400), "d"], [Math.floor((up % 86400) / 3600), "h"], [Math.floor((up % 3600) / 60), "m"]].filter(([n]) => n);
  const uptime = parts.slice(0, 2).map(([n, u]) => n + u).join(" ") || "<1m";
  setTopExtra("server", {
    meta: [h("span", { class: "dot ok" }), h("span", { class: "meta" }, `running · up ${uptime}`)],
    right: h("button", { class: "btn", onclick: () => conn.rpc("server.stop").catch(() => {}),
      title: "Agents stop too" }, "Stop") });
  const kv = (rows) => h("div", { class: "kv" }, ...rows.flatMap(([k, v, mono]) => [h("span", {}, k), h("span", { class: mono ? "mono trunc" : "" }, v)]));
  root.replaceChildren(h("div", { class: "view dview" },
    h("div", { class: "bx" }, h("div", { class: "bh" }, "Status"), kv([
      ["Process", `pid ${info.pid} · hd ${info.version}`, 1], ["Listening", `127.0.0.1:${info.port} (this machine only)`, 1],
      ["Session file", `session.json · ${info.session_saved ? "saved" : "not saved yet"}`, 1],
      ["Config", info.config_dir, 1],
      ["Agents", Object.entries(info.counts).map(([k, v]) => `${v} ${k}`).join(" · ") || "none"]])),
    h("div", { class: "bx" }, h("div", { class: "bh" }, `Connected clients · ${info.clients.length}`),
      ...info.clients.map((c) => h("div", { class: "rr", style: { padding: 0 } }, h("span", { class: "dot ok" }), h("span", { class: "grow" }, c.label)))),
    [...info.rule_errors, ...info.settings_errors].map((e) => h("div", { class: "errtext", style: { gridColumn: "span 2" } }, e)),
    h("div", { class: "row", style: { gridColumn: "span 2" } }, h("button", { class: "btn", onclick: () => conn.rpc("notify.test").catch(errorToast) }, "Test notification"),
      h("span", { class: "meta" }, "Closing the window never stops agents. Stopping the server does."))));
}

const restoreAsked = new Set();

export function maybeShowRestore(actions) {
  const stopped = store.raw.stopped || [];
  if (!stopped.some((s) => !restoreAsked.has(s.id))) return; // ask about each stopped pane only once
  stopped.forEach((s) => restoreAsked.add(s.id));
  const boxes = stopped.map((s) => ({ s, box: h("input", { type: "checkbox", checked: s.kind !== "shell" ? true : null }) }));
  const resume = h("button", { class: "btn pri", onclick: () => { closeModal(); actions.resume(boxes.filter((b) => b.box.checked).map((b) => b.s.id)); } });
  const count = () => { const n = boxes.filter((b) => b.box.checked).length; resume.textContent = `Resume ${n} agent${n === 1 ? "" : "s"}`; resume.disabled = !n; };
  boxes.forEach((b) => b.box.addEventListener("change", count));
  count();
  openModal({
    size: "sm", label: "Pick up where you left off?",
    head: h("div", { class: "rhead" }, h("div", { class: "rt1" }, "Pick up where you left off?"),
      h("div", { class: "rt2" }, "Your computer restarted, so these agents stopped. herd can start them again and resume their sessions. Layout, tabs and worktrees are already restored.")),
    body: h("div", { class: "rlist" },
      ...boxes.map(({ s, box }) => h("label", { class: "rr" }, box, kindIcon(s.kind),
        h("span", { class: "grow" }, s.name), h("span", { class: "mono meta" }, s.kind === "shell" ? "new shell, same folder" : (s.resume || s.command))))),
    foot: [h("span", { class: "grow" }), h("button", { class: "btn", onclick: () => { closeModal(); actions.discard(null); } }, "Start fresh"), resume],
  });
}

