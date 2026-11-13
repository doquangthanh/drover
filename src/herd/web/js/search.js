// "Jump to a terminal" (Ctrl+B /): agents, spaces and scrollback matches across all machines, with a live preview.
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
  const list = h("div", { class: "sp-l" });
  const pvHead = h("div", { class: "ph" });
  const pv = h("div", { class: "pv" });
  let items = [];
  let selected = 0;
  let timer = null;
  let pvPane = null;

  const go = (item) => { closeModal(); item.go(); };
  const preview = (paneId) => {
    if (paneId === pvPane) return;
    pvPane = paneId;
    const p = store.pane(paneId);
    pvHead.replaceChildren(...(p ? [kindIcon(p.kind), h("b", { style: { fontWeight: 500 } }, p.name),
      h("span", { class: "grow trunc meta" }, `${p.cwd} · live preview`), stateMark(p)] : []));
    pv.textContent = "";
    if (!p) return;
    conn.rpc("pane.read", { pane: paneId, lines: 24 }).then((r) => { if (pvPane === paneId) pv.textContent = r.text.replace(/\s+$/, ""); })
      .catch(() => {});
  };
  const render = (q, text = []) => {
    const ql = q.toLowerCase();
    const agents = store.panes.filter((p) => !q || p.name.toLowerCase().includes(ql) || p.kind.includes(ql)
      || (p.cwd || "").toLowerCase().includes(ql));
    const spaces = store.spaces.filter((s) => q && (s.name.toLowerCase().includes(ql) || s.cwd.toLowerCase().includes(ql)));
    items = [];
    const rows = [];
    let lastSection = "";
    const add = (section, el, goFn, paneId = null) => {
      if (section && section !== lastSection) { lastSection = section; rows.push(h("div", { class: "sec" }, section)); }
      const i = items.length;
      items.push({ go: goFn, pane: paneId });
      rows.push(h("button", { class: "it" + (i === selected ? " on" : ""), onclick: () => go(items[i]) }, ...el));
    };
    for (const p of agents.slice(0, 12)) {
      const parent = p.parent && store.pane(p.parent);
      add("Agents", [kindIcon(p.kind), h("span", { class: "lb" }, highlight(p.name, q)),
        h("span", { class: "meta" }, parent ? `child of ${parent.name}` : store.space(p.space_id)?.name || ""), stateMark(p)],
      () => actions.focusPane(p.id), p.id);
    }
    for (const s of spaces.slice(0, 6)) {
      add("Spaces & worktrees", [spaceAvatar(s), h("span", { class: "lb" }, highlight(s.name, q)),
        h("span", { class: "meta mono trunc" }, s.branch || s.cwd)], () => actions.selectSpace(s.id));
    }
    const shown = text.slice(0, 6);
    for (const t of shown) {
      add(`In scrollback · ${text.length} match${text.length > 1 ? "es" : ""}`, [h("span", { class: "meta mono", style: { width: "56px" } }, t.name),
        h("span", { class: "lb mono" }, highlight(t.text, q))], () => { actions.focusPane(t.pane); actions.find({ paneId: t.pane, query: q }); }, t.pane);
    }
    if (text.length > shown.length) rows.push(h("div", { class: "it meta", style: { paddingLeft: "76px" } }, `${text.length - shown.length} more…`));
    if (!items.length) rows.push(h("div", { class: "sec" }, q ? "Nothing found" : "No agents yet"));
    selected = Math.min(selected, Math.max(0, items.length - 1));
    list.replaceChildren(...rows);
    preview(items[selected]?.pane || null);
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
    size: "srch", label: "Jump to a terminal",
    head: h("div", { class: "mhead" }, icon("search"), input, h("span", { class: "meta" }, "agents · spaces · scrollback"),
      h("span", { class: "k" }, "Esc")),
    body: h("div", { class: "sp" }, list, h("div", { class: "sp-r" }, pvHead, pv)),
  });
  document.querySelector(".modal.srch").append(h("div", { class: "hint" }, h("span", {}, "↑↓ move"), h("span", {}, "↵ jump"), h("span", { class: "grow" }), "local scrollback search"));
  render("");
}
