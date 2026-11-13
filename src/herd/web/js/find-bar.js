// Find-in-scrollback bar shown under a pane header (Ctrl+B [).
import { h, icon } from "./dom.js";
import { getTerminal, findInPane } from "./terminals.js";

export function findBar(paneId, actions) {
  const status = h("span", { class: "fcount" }, "");
  const lines = h("span", { class: "meta" });
  const show = (r) => { status.textContent = r.total ? `${r.index} of ${r.total}` : input.value ? "no match" : ""; };
  const step = (dir) => show(findInPane(paneId, input.value, true, dir));
  const input = h("input", { id: "find-q", "aria-label": "Find in scrollback", autocomplete: "off",
    oninput: () => { show(findInPane(paneId, input.value)); lines.textContent = depth(); },
    onkeydown: (e) => {
      if (e.key === "Escape") actions.find({ paneId });
      if (e.key === "Enter") step(e.shiftKey ? 1 : -1);
    } });
  const depth = () => { const t = getTerminal(paneId).term; return `scrollback ${t.buffer.active.length.toLocaleString("fr-FR")} / ${t.options.scrollback.toLocaleString("fr-FR")}`; };
  lines.textContent = depth();
  setTimeout(() => input.focus(), 0);
  const k = (t) => h("span", { class: "k" }, t);
  return h("div", { class: "findbar" }, h("label", { class: "flab", for: "find-q" }, icon("search", "i sm"), "Find"), input, status,
    h("button", { class: "pb", "aria-label": "Older match", onclick: () => step(-1) }, "↑"),
    h("button", { class: "pb", "aria-label": "Newer match", onclick: () => step(1) }, "↓"),
    h("span", { class: "grow" }),
    h("span", { class: "meta" }, lines, " · ", k("Enter"), " older ", k("⇧ Enter"), " newer ", k("Esc"), " exit"));
}
