// Changes: worktrees of the current space's repo, files changed vs base, diff, commit / push / PR.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, stateMark, errorToast, toast } from "../dom.js";
import { confirmBox, promptText } from "../modal.js";

const st = { path: null, file: null, base: "" };

function rpc(method, params, machine) { return conn.rpc(method, machine ? { ...params, machine } : params); }

function diffEl(text) {
  const lines = (text || "").split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l));
  if (!lines.join("").trim()) return h("div", { class: "meta", style: { padding: "14px" } }, "No changes in this file.");
  return h("div", { class: "diff" }, ...lines.map((l) => h("div", {
    class: l.startsWith("+") ? "a" : l.startsWith("-") ? "r" : l.startsWith("@@") ? "h" : "" }, l || " ")));
}

export async function renderChanges(root, actions) {
  const space = store.space(store.ui.spaceId);
  if (!space) { root.replaceChildren(h("div", { class: "view meta" }, "Open a space first.")); return; }
  const machine = space.machine && space.machine !== "local" ? space.machine : null;
  root.replaceChildren(h("div", { class: "view meta" }, "Loading git info…"));
  let info, trees;
  try {
    info = await rpc("git.info", { path: space.cwd }, machine);
    if (!info.is_repo) { root.replaceChildren(h("div", { class: "view meta" }, `${space.cwd} is not a git repository.`)); return; }
    trees = await rpc("worktree.list", { repo: info.root }, machine);
  } catch (e) { root.replaceChildren(h("div", { class: "view errtext" }, e.message)); return; }
  const mainTree = trees[0];
  st.base = st.base || mainTree?.branch || "main";
  if (!st.path || !trees.some((t) => t.path === st.path)) st.path = (trees[1] || trees[0]).path;
  const current = trees.find((t) => t.path === st.path);
  const agentsIn = (path) => store.panes.filter((p) => p.cwd && p.cwd.replace(/\\/g, "/").startsWith(path.replace(/\\/g, "/")));

  const list = h("div", { class: "pb-body" }, ...trees.map((t, i) => {
    const agent = i ? agentsIn(t.path)[0] : null;
    return h("button", { class: "srow" + (t.path === st.path ? " on" : ""), style: { height: "auto", padding: "8px 10px", flexDirection: "column", alignItems: "stretch", gap: "3px" },
      onclick: () => { st.path = t.path; st.file = null; renderChanges(root, actions); } },
    h("span", { class: "row" }, agent ? kindIcon(agent.kind) : null, h("span", { class: "grow trunc mono" }, t.branch || "(detached)"),
      agent ? stateMark(agent) : null),
    h("span", { class: "meta trunc" }, `${t.changes ? t.changes + " uncommitted · " : "clean · "}${t.path}`));
  }),
  h("div", { class: "row", style: { padding: "10px 4px", flexWrap: "wrap" } },
    h("button", { class: "btn", onclick: async () => {
      const task = await promptText("New task worktree", "", "Task name");
      if (!task) return;
      try { const r = await rpc("worktree.create", { repo: info.root, task, base: st.base }, machine); toast(`Created ${r.branch}`); st.path = r.path; renderChanges(root, actions); }
      catch (e) { errorToast(e); }
    } }, "+ New worktree"),
    current && current !== mainTree ? h("button", { class: "btn", onclick: () => actions.newAgent({ cwd: current.path, machine }) }, "Agent here") : null,
    current && current !== mainTree ? h("button", { class: "btn danger", onclick: async () => {
      if (!(await confirmBox("Remove worktree?", `${current.path} will be deleted. Uncommitted work blocks this unless you force it.`, "Remove", true))) return;
      try { await rpc("worktree.remove", { path: current.path }, machine); st.path = null; renderChanges(root, actions); }
      catch (e) {
        if (await confirmBox("It has uncommitted files", e.message + "\nForce remove anyway?", "Force remove", true)) {
          rpc("worktree.remove", { path: current.path, force: true }, machine).then(() => renderChanges(root, actions)).catch(errorToast);
        }
      }
    } }, "Remove") : null));

  const files = await rpc("worktree.changes", { path: st.path, base: st.base }, machine).catch(() => []);
  if (!st.file && files.length) st.file = files[0].path;
  const diffBox = h("div", { style: { flex: "1", minWidth: "0", overflow: "auto", padding: "10px 0" } });
  const fileList = h("div", { style: { width: "260px", flex: "none", borderRight: "1px solid var(--border)", padding: "6px", overflow: "auto" } },
    ...files.map((f) => h("button", { class: "fileitem" + (f.path === st.file ? " on" : ""), onclick: () => { st.file = f.path; renderChanges(root, actions); } },
      h("span", { class: "mono grow trunc" }, f.path), h("span", { class: "add mono" }, `+${f.added}`), h("span", { class: "rem mono" }, `-${f.removed}`))),
    files.length ? null : h("div", { class: "meta", style: { padding: "8px" } }, "No changes vs " + st.base));
  if (st.file) rpc("worktree.diff", { path: st.path, base: st.base, file: st.file }, machine)
    .then((r) => diffBox.replaceChildren(diffEl(r.diff))).catch((e) => diffBox.replaceChildren(h("div", { class: "errtext" }, e.message)));

  const act = (label, fn, pri) => h("button", { class: "btn" + (pri ? " pri" : ""), onclick: async () => {
    try { const r = await fn(); if (r?.output) toast(label, r.output.slice(0, 200)); renderChanges(root, actions); } catch (e) { errorToast(e); }
  } }, label);
  const baseIn = h("input", { class: "in mono", style: { width: "120px", height: "28px" }, value: st.base, "aria-label": "Compare against",
    onchange: () => { st.base = baseIn.value.trim() || "main"; renderChanges(root, actions); } });
  root.replaceChildren(h("div", { class: "vsplit" },
    h("div", { class: "panel", style: { width: "320px", flex: "none" } }, h("div", { class: "ph" }, h("b", {}, space.name), h("span", { class: "meta" }, "worktrees")), list),
    h("div", { class: "panel focus grow" },
      h("div", { class: "ph", style: { flexWrap: "wrap", height: "auto", minHeight: "42px" } },
        h("span", { class: "mono", style: { color: "var(--accent)" } }, current?.branch || ""), h("span", { class: "meta" }, "vs"), baseIn,
        h("span", { class: "grow" }),
        act("Commit…", async () => { const m = await promptText("Commit message", "", "Message"); return m ? rpc("git.commit", { path: st.path, message: m }, machine) : null; }),
        act(`Rebase on ${st.base}`, () => rpc("git.rebase", { path: st.path, base: st.base }, machine)),
        act("Push", () => rpc("git.push", { path: st.path }, machine)),
        act("Open PR", () => rpc("git.pr", { path: st.path }, machine), true)),
      h("div", { style: { display: "flex", flex: "1", minHeight: "0" } }, fileList, diffBox))));
}
