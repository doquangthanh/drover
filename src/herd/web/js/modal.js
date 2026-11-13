// Shared modal shell + small prompt/confirm dialogs.
import { h } from "./dom.js";

let current = null;

export function closeModal() {
  if (current) { current.remove(); current = null; }
}

export function openModal({ title = "", head = null, body = [], foot = null, size = "", onClose = null, label = "" }) {
  closeModal();
  const modal = h("div", { class: `modal ${size}`, role: "dialog", "aria-modal": "true", "aria-label": label || title },
    head || (title ? h("div", { class: "mhead" }, h("h2", {}, title)) : null),
    ...[].concat(body),
    foot ? h("div", { class: "mfoot" }, foot) : null);
  const scrim = h("div", { class: "scrim", onmousedown: (e) => { if (e.target === scrim) done(); } }, modal);
  const done = () => { closeModal(); onClose && onClose(); };
  scrim.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.stopPropagation(); done(); }
  });
  document.getElementById("overlay-root").append(scrim);
  current = scrim;
  setTimeout(() => (modal.querySelector("[autofocus], input, textarea, button") || modal).focus(), 0);
  return { modal, close: done };
}

export function promptText(title, value = "", label = "Name") {
  return new Promise((resolve) => {
    const input = h("input", { class: "in", value, "aria-label": label, autofocus: true });
    let settled = false;
    const finish = (v) => { if (!settled) { settled = true; closeModal(); resolve(v); } };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") finish(input.value.trim()); });
    openModal({
      title, size: "", body: h("div", { class: "mbody" }, h("label", { class: "lab" }, label), input),
      foot: [h("span", { class: "grow" }), h("button", { class: "btn", onclick: () => finish(null) }, "Cancel"),
        h("button", { class: "btn pri", onclick: () => finish(input.value.trim()) }, "Save")],
      onClose: () => finish(null),
    });
  });
}

export function confirmBox(title, text, okLabel = "OK", danger = false) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (v) => { if (!settled) { settled = true; closeModal(); resolve(v); } };
    openModal({
      title, body: h("div", { class: "mbody" }, h("div", { style: { lineHeight: "1.5" } }, text)),
      foot: [h("span", { class: "grow" }), h("button", { class: "btn", onclick: () => finish(false) }, "Cancel"),
        h("button", { class: "btn " + (danger ? "danger" : "pri"), autofocus: true, onclick: () => finish(true) }, okLabel)],
      onClose: () => finish(false),
    });
  });
}
