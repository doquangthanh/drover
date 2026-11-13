// herd-server status + "Pick up where you left off?" restore dialog + shortcuts help + broadcast.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, errorToast } from "../dom.js";
import { openModal, closeModal } from "../modal.js";
import { SHORTCUTS } from "../keys.js";

export async function renderServer(root) {
  let info;
  try { info = await conn.rpc("server.info"); } catch (e) { root.replaceChildren(h("div", { class: "view errtext" }, e.message)); return; }
  const up = Math.floor(info.uptime);
  const uptime = `${Math.floor(up / 86400)}d ${Math.floor((up % 86400) / 3600)}h ${Math.floor((up % 3600) / 60)}m`;
  root.replaceChildren(h("div", { class: "view" }, h("div", { class: "grid2" },
    h("div", { class: "card" }, h("div", { class: "sechead", style: { padding: 0 } }, "Status"), h("div", { class: "kv" },
      h("span", {}, "Process"), h("span", { class: "mono" }, `pid ${info.pid} · hd ${info.version}`),
      h("span", {}, "Listening"), h("span", { class: "mono" }, `127.0.0.1:${info.port}`),
      h("span", {}, "Uptime"), h("span", {}, uptime),
      h("span", {}, "Config"), h("span", { class: "mono trunc" }, info.config_dir),
      h("span", {}, "Agents"), h("span", {}, Object.entries(info.counts).map(([k, v]) => `${v} ${k}`).join(" · ") || "none"))),
    h("div", { class: "card" }, h("div", { class: "sechead", style: { padding: 0 } }, `Connected clients · ${info.clients.length}`),
      ...info.clients.map((c) => h("div", { class: "lrow", style: { padding: 0 } }, h("span", { class: "dot ok" }), c.label)))),
  [...info.rule_errors, ...info.settings_errors].map((e) => h("div", { class: "errtext" }, e)),
  h("div", { class: "row" }, h("button", { class: "btn", onclick: () => conn.rpc("notify.test").catch(errorToast) }, "Test notification"),
    h("button", { class: "btn danger", onclick: () => conn.rpc("server.stop").catch(() => {}) }, "Stop server (agents stop too)")),
  h("p", { class: "meta" }, "Closing the window never stops agents. Stopping the server does.")));
}

const restoreAsked = new Set();

export function maybeShowRestore(actions) {
  const stopped = store.raw.stopped || [];
  if (!stopped.some((s) => !restoreAsked.has(s.id))) return; // ask about each stopped pane only once
  stopped.forEach((s) => restoreAsked.add(s.id));
  const boxes = stopped.map((s) => ({ s, box: h("input", { type: "checkbox", checked: s.kind !== "shell" ? true : null }) }));
  openModal({
    title: "Pick up where you left off?",
    body: h("div", { class: "mbody" },
      h("div", { class: "meta", style: { lineHeight: "1.5" } },
        "herd-server restarted, so these agents stopped. herd can start them again and resume their sessions. Layout and tabs are already restored."),
      ...boxes.map(({ s, box }) => h("label", { class: "ck", style: { height: "32px" } }, box, kindIcon(s.kind),
        h("span", { class: "grow" }, s.name), h("span", { class: "mono meta" }, s.kind === "shell" ? "new shell, same folder" : (s.resume || s.command))))),
    foot: [h("span", { class: "grow" }),
      h("button", { class: "btn", onclick: () => { closeModal(); actions.discard(null); } }, "Start fresh"),
      h("button", { class: "btn pri", onclick: () => { closeModal(); actions.resume(boxes.filter((b) => b.box.checked).map((b) => b.s.id)); } },
        "Resume selected")],
  });
}

export function openShortcuts() {
  openModal({
    size: "xwide", title: "Keyboard shortcuts",
    body: [h("div", { class: "meta", style: { padding: "10px 20px 0" } }, "Press Ctrl+B first, then the key. Everything else goes to the agent. Ctrl+B twice sends a real Ctrl+B."),
      h("div", { class: "keysgrid" }, ...SHORTCUTS.map(([group, items]) => h("div", {},
        h("div", { class: "sec", style: { padding: "4px 0 8px" } }, group),
        ...items.map(([key, label]) => h("div", { class: "kr" }, h("span", {}, label), h("span", { class: "k" }, key.replace("Arrow", "")))))))],
  });
}

export function openBroadcast() {
  const panes = store.panes.filter((p) => p.state !== "exited");
  const boxes = panes.map((p) => ({ p, box: h("input", { type: "checkbox", checked: p.kind !== "shell" ? true : null }) }));
  const text = h("textarea", { class: "in", rows: "3", placeholder: "Prompt to send", "aria-label": "Prompt" });
  openModal({
    title: "Send to several agents",
    body: h("div", { class: "mbody" }, text, ...boxes.map(({ p, box }) => h("label", { class: "ck" }, box, kindIcon(p.kind), p.name,
      h("span", { class: "meta" }, store.space(p.space_id)?.name || "")))),
    foot: [h("span", { class: "grow" }), h("button", { class: "btn", onclick: closeModal }, "Cancel"),
      h("button", { class: "btn pri", onclick: () => {
        const t = text.value.trim();
        if (t) boxes.filter((b) => b.box.checked).forEach((b) => conn.rpc("pane.send", { pane: b.p.id, text: t }).catch(errorToast));
        closeModal();
      } }, "Send")],
  });
}
