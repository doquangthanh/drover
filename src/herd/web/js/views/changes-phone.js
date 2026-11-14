// Changes on a phone: two steps instead of one cramped screen.
//   list : branch + totals, the files (name first, folder under it), a bottom bar with Commit / Push & open PR / More
//   diff : one file full screen, previous / next file, line wrap on by default (no sideways scrolling to read code)
import { h } from "../dom.js";
import { openModal, closeModal, promptText } from "../modal.js";
import { diffEl } from "./changes-view.js";

const split = (p) => { const i = p.lastIndexOf("/"); return i < 0 ? ["", p] : [p.slice(0, i + 1), p.slice(i + 1)]; };
const totals = (files) => files.reduce((t, f) => ({ a: t.a + (f.added || 0), r: t.r + (f.removed || 0) }), { a: 0, r: 0 });

function diffScreen(c) {
  const { st, files, redraw, rpc, machine } = c;
  const i = Math.max(0, files.findIndex((f) => f.path === st.file));
  const [dir, name] = split(files[i].path);
  const go = (n) => { st.file = files[(n + files.length) % files.length].path; redraw(true); };
  const box = h("div", { class: "cdb" });
  rpc("worktree.diff", { path: st.path, base: st.base, file: st.file }, machine)
    .then((r) => box.replaceChildren(diffEl(r.diff))).catch((e) => box.replaceChildren(h("div", { class: "errtext", style: { padding: "14px" } }, e.message)));
  const wrapBtn = h("button", { class: "chip sm" + (st.wrap ? " on" : ""), "aria-pressed": String(st.wrap),
    onclick: () => { st.wrap = !st.wrap; box.classList.toggle("wrap", st.wrap); wrapBtn.classList.toggle("on", st.wrap); wrapBtn.setAttribute("aria-pressed", String(st.wrap)); } }, "Wrap");
  box.classList.toggle("wrap", st.wrap);
  return h("div", { class: "cphone" },
    h("div", { class: "cdh" },
      h("button", { class: "ibtn", "aria-label": "Back to files", onclick: () => { st.stage = "list"; redraw(true); } }, "‹"),
      h("div", { class: "grow cdt" }, h("div", { class: "trunc cdn" }, name), h("div", { class: "trunc meta mono" }, `${i + 1}/${files.length} · ${dir || "/"}`)),
      wrapBtn,
      h("button", { class: "ibtn", "aria-label": "Previous file", disabled: files.length < 2 ? true : null, onclick: () => go(i - 1) }, "↑"),
      h("button", { class: "ibtn", "aria-label": "Next file", disabled: files.length < 2 ? true : null, onclick: () => go(i + 1) }, "↓")),
    box);
}

function moreSheet(c) {
  const { st, current, mainTree, newWorktree, rpc, machine, actions, act, redraw } = c;
  const row = (label, fn, cls = "") => h("button", { class: "sheet-row " + cls, onclick: () => { closeModal(); setTimeout(fn, 0); } }, h("span", { class: "grow" }, label));
  const rows = [
    row("New task worktree", newWorktree),
    row(`Compare against: ${st.base}`, async () => { const b = await promptText("Compare against", st.base, "Branch or commit"); if (b) { st.base = b.trim(); redraw(); } }),
  ];
  if (current && current.branch !== st.base) rows.unshift(row(`Rebase on ${st.base}`, () => act.run(`Rebase on ${st.base}`, () => rpc("git.rebase", { path: st.path, base: st.base }, machine))));
  if (current && current !== mainTree) {
    rows.push(row("Open an agent here", () => actions.newAgent({ cwd: current.path, machine })));
    rows.push(row("Remove this worktree…", () => { st.confirm = true; st.wtOpen = true; redraw(); }, "danger"));
  }
  openModal({ title: "Actions", size: "sheet", body: h("div", { class: "sheet-list" }, ...rows) });
}

function listScreen(c) {
  const { st, files, current, trees, list, redraw, act } = c;
  const t = totals(files);
  const baseBtn = h("button", { class: "chip sm", "aria-label": "Compare against", onclick: async () => {
    const b = await promptText("Compare against", st.base, "Branch or commit"); if (b) { st.base = b.trim(); redraw(); } } }, st.base);
  const wt = trees.length > 1 ? h("button", { class: "cwt-toggle", "aria-expanded": String(st.wtOpen), onclick: () => { st.wtOpen = !st.wtOpen; redraw(true); } },
    h("span", { class: "meta" }, "Worktree"), h("span", { class: "grow trunc mono" }, current?.branch || ""), h("span", { class: "meta" }, st.wtOpen ? "▴" : "▾")) : null;
  const rows = files.map((f) => {
    const [dir, name] = split(f.path);
    return h("button", { class: "cfr", onclick: () => { st.file = f.path; st.stage = "diff"; redraw(true); } },
      h("span", { class: "cs " + (f.status || "M") }, f.status || "M"),
      h("span", { class: "grow cfn" }, h("span", { class: "trunc cfb" }, name), h("span", { class: "trunc meta mono" }, dir || "/")),
      h("span", { class: "add mono" }, `+${f.added || 0}`), f.removed ? h("span", { class: "rem mono" }, `−${f.removed}`) : null);
  });
  return h("div", { class: "cphone" },
    h("div", { class: "chead" }, h("span", { class: "gb" }, h("span", { class: "gb-name" }, current?.branch || "")), h("span", { class: "meta" }, "vs"), baseBtn,
      h("span", { class: "grow" }),
      h("span", { class: "meta" }, `${files.length} file${files.length === 1 ? "" : "s"}`), t.a ? h("span", { class: "add mono" }, `+${t.a}`) : null,
      t.r ? h("span", { class: "rem mono" }, `−${t.r}`) : null),
    wt, st.wtOpen ? h("div", { class: "cwt-open" }, list) : null,
    files.length ? h("div", { class: "cfl" }, ...rows)
      : h("div", { class: "cempty" }, h("div", { class: "cempty-t" }, "Nothing to commit"), h("div", { class: "meta" }, `No changes compared with ${st.base}.`)),
    h("div", { class: "cbar" },
      act.btn("Commit…", async () => { const m = await promptText("Commit message", "", "Message"); return m ? c.rpc("git.commit", { path: st.path, message: m }, c.machine) : null; }, false, !files.length),
      act.btn("Push & open PR", async () => { await c.rpc("git.push", { path: st.path }, c.machine); return c.rpc("git.pr", { path: st.path }, c.machine); }, true),
      h("button", { class: "btn cmore", "aria-label": "More actions", onclick: () => moreSheet(c) }, "⋯")));
}

/** c: everything renderChanges already computed (state, git data, rpc helper, actions). */
export function renderPhoneChanges(c) {
  const { root, st, files } = c;
  if (st.stage === "diff" && !files.some((f) => f.path === st.file)) st.stage = "list"; // the file is no longer changed
  root.replaceChildren(st.stage === "diff" ? diffScreen(c) : listScreen(c));
}
