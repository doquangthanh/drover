// "Jump to a terminal" (Ctrl+B /): agents, spaces and scrollback matches across all machines.
import { conn } from "./connection.js";
import { store } from "./store.js";
import { h, icon, kindIcon, stateMark, spaceAvatar } from "./dom.js";
import { openModal, closeModal } from "./modal.js";

function highlight(text, q) {
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (!q || i < 0) return text;
  return [text.slice(0, i), h("mark", {}, text.slice(i, i + q.length)), text.slice(i + q.length)];
}

export function openSearch(actions) {
  const input = h("input", { class: "qin", placeholder: "Jump to a terminal…", "aria-label": "Jump to a terminal", autofocus: true });
  const list = h("div", { class: "list", style: { flex: "1" } });
  let items = [];
  let selected = 0;
  let timer = null;

  const go = (item) => { closeModal(); item.go(); };
  const render = (q, text = []) => {
    const ql = q.toLowerCase();
    const agents = store.panes.filter((p) => !q || p.name.toLowerCase().includes(ql) || p.kind.includes(ql)
      || (p.cwd || "").toLowerCase().includes(ql));
    const spaces = store.spaces.filter((s) => q && (s.name.toLowerCase().includes(ql) || s.cwd.toLowerCase().includes(ql)));
    items = [];
    const rows = [];
    let lastSection = "";
    const add = (section, el, goFn) => {
      if (section && section !== lastSection) { lastSection = section; rows.push(h("div", { class: "sec" }, section)); }
      const i = items.length;
      items.push({ go: goFn });
      rows.push(h("button", { class: "it" + (i === selected ? " on" : ""), onclick: () => go(items[i]) }, ...el));
    };
    for (const p of agents.slice(0, 12)) {
      add("Agents", [kindIcon(p.kind), h("span", { class: "lb trunc" }, highlight(p.name, q)),
        h("span", { class: "meta" }, store.space(p.space_id)?.name || ""), stateMark(p)], () => actions.focusPane(p.id));
    }
    for (const s of spaces.slice(0, 6)) {
      add("Spaces", [spaceAvatar(s), h("span", { class: "lb trunc" }, highlight(s.name, q)), h("span", { class: "meta mono trunc" }, s.cwd)],
        () => actions.selectSpace(s.id));
    }
    for (const t of text) {
      add(`In scrollback · ${text.length}`, [h("span", { class: "meta mono", style: { width: "70px" } }, t.name),
        h("span", { class: "lb mono trunc" }, highlight(t.text, q))], () => { actions.focusPane(t.pane); actions.find({ paneId: t.pane, query: q }); });
    }
    if (!items.length) rows.push(h("div", { class: "sec" }, q ? "Nothing found" : "No agents yet"));
    selected = Math.min(selected, Math.max(0, items.length - 1));
    list.replaceChildren(...rows);
  };

  input.addEventListener("input", () => {
    selected = 0;
    const q = input.value.trim();
    render(q);
    clearTimeout(timer);
    if (q.length >= 2) {
      timer = setTimeout(() => conn.rpc("search.query", { q }).then((r) => {
        if (input.value.trim() === q) render(q, r.text || []);
      }).catch(() => {}), 200);
    }
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { selected = Math.min(selected + 1, items.length - 1); render(input.value.trim()); e.preventDefault(); }
    if (e.key === "ArrowUp") { selected = Math.max(selected - 1, 0); render(input.value.trim()); e.preventDefault(); }
    if (e.key === "Enter" && items[selected]) go(items[selected]);
  });
  openModal({
    size: "wide", label: "Jump to a terminal",
    head: h("div", { class: "mhead" }, icon("search"), input, h("span", { class: "meta" }, "agents · spaces · scrollback"),
      h("span", { class: "k" }, "Esc")),
    body: list,
  });
  list.after(h("div", { class: "hint" }, "↑↓ move", "↵ jump", h("span", { class: "grow" }), "local scrollback search"));
  render("");
}
