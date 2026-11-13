// Keyboard shortcuts sheet and the "send a prompt to several agents" dialog.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, errorToast } from "../dom.js";
import { openModal, closeModal } from "../modal.js";
import { SHORTCUTS } from "../keys.js";

const ARROWS = { ArrowLeft: "←", ArrowRight: "→", ArrowUp: "↑", ArrowDown: "↓" };

/** "Go to tab 1–9" -> label "Go to tab" with chips [key, "1–9"]. */
function chips(key, label) {
  const m = /^(.*?)\s*(?:\(then )?(1–[39])\)?$/.exec(label);
  const k = (t) => h("span", { class: "k lg" }, t);
  if (!m) return [label, [k(ARROWS[key] || key)]];
  const [from, to] = m[2].split("–");
  const range = [k(from), "–", k(to)];
  return [m[1], key === "1" ? range : [k(key), ...range]];
}

export function openShortcuts() {
  const k = (t) => h("span", { class: "k lg" }, t);
  openModal({
    size: "keys", label: "Keyboard shortcuts",
    head: h("div", { class: "mhead" }, h("h2", {}, "Keyboard shortcuts"),
      h("span", { class: "meta" }, "Press ", k("Ctrl"), " ", k("B"), " first, then the key. Everything else goes to the agent.")),
    body: [h("div", { class: "keysgrid" }, ...SHORTCUTS.map(([group, items]) => h("div", { class: "kcol" },
      h("div", { class: "kh" }, group),
      ...items.map(([key, label]) => { const [text, keys] = chips(key, label);
        return h("div", { class: "kr" }, h("span", {}, text), h("span", { class: "keys" }, ...keys)); })))),
    h("div", { class: "kfoot" }, "Change any of these in ", h("span", { class: "mono" }, "keys.toml"), ". ", k("Ctrl"), " ", k("B"),
      " twice sends a real Ctrl+B to the agent.")],
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
