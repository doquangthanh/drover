// Changes: worktrees of the current space's repo, files changed vs base, diff, commit / push / PR.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, stateMark, errorToast, toast, setTopExtra } from "../dom.js";
import { confirmBox, promptText } from "../modal.js";

const st = { path: null, file: null, base: "", cache: null, confirm: false }; // cache: last git data, reused when only the file changes

function rpc(method, params, machine) { return conn.rpc(method, machine ? { ...params, machine } : params); }

/** Unified diff with line numbers (new-file numbers; old-file numbers for removed lines). */
export function diffEl(text) {
  const lines = (text || "").split("\n").filter((l) => !/^(diff --git|index |--- |\+\+\+ )/.test(l));
  if (!lines.join("").trim()) return h("div", { class: "meta", style: { padding: "14px" } }, "No changes in this file.");
  let oldN = 0, newN = 0;
  return h("div", { class: "diff" }, ...lines.map((l) => {
    const hunk = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(l);
    if (hunk) { oldN = +hunk[1]; newN = +hunk[2]; return h("div", { class: "h" }, l); }
    const kind = l[0] === "+" ? "a" : l[0] === "-" ? "r" : "";
    let n;
    if (kind === "r") n = oldN++; else if (kind === "a") n = newN++; else { n = newN++; oldN++; }
    return h("div", { class: kind }, h("span", { class: "ln" }, String(n).padStart(3, " ")), " " + (l || " "));
  }));
}

function treeRow(t, i, { path, agent, onpick }) {
  const on = t.path === path;
  const count = t.changes ? h("span", { style: { color: "var(--yellow)" } }, `${t.changes} files`) : "clean";
  return h("button", { class: "wt" + (on ? " on" : ""), disabled: t.missing ? true : null, style: t.missing ? { opacity: ".5" } : null, onclick: onpick },
    h("span", { class: "top" }, agent ? kindIcon(agent.kind) : null,
      h("span", { class: "grow trunc" + (agent ? "" : " mono") }, agent ? agent.name : t.branch || "(detached)"),
      agent ? stateMark(agent) : h("span", { class: "meta" }, t.missing ? "folder deleted" : count)),
    h("span", { class: "meta trunc" }, agent ? [h("span", { class: "mono", style: { color: on ? "var(--accent)" : "" } }, t.branch), " · ", count]
      : h("span", { class: "mono" }, t.path)));
}

/** `reuse`: only the selected file changed — keep the git data, just fetch its diff. */
export async function renderChanges(root, actions, reuse = false) {
  const space = store.space(store.ui.spaceId);
  if (!space) { root.replaceChildren(h("div", { class: "view meta" }, "Open a space first.")); return; }
  const machine = space.machine && space.machine !== "local" ? space.machine : null;
  const cached = reuse && st.cache?.spaceId === space.id && st.cache.path === st.path ? st.cache : null;
  let info, trees;
  if (cached) ({ info, trees } = cached);
  else {
    if (!root.querySelector(".vsplit")) root.replaceChildren(h("div", { class: "view meta" }, "Loading git info…"));
    try {
      // Both in parallel: `git worktree list` works from any folder inside the repo.
      const listing = rpc("worktree.list", { repo: space.cwd }, machine);
      listing.catch(() => {}); // a non-repo rejects here; git.info reports that case below
      info = await rpc("git.info", { path: space.cwd }, machine);
      if (!info.is_repo) { root.replaceChildren(h("div", { class: "view meta" }, `${space.cwd} is not a git repository.`)); return; }
      trees = await listing;
    } catch (e) { root.replaceChildren(h("div", { class: "view errtext" }, e.message)); return; }
  }
  const mainTree = trees[0];
  st.base = st.base || mainTree?.branch || "main";
  const live = trees.filter((t) => !t.missing); // worktrees whose folder was deleted cannot be opened
  const missing = trees.length - live.length;
  if (!st.path || !live.some((t) => t.path === st.path)) st.path = (live[1] || live[0] || trees[0]).path;
  const current = trees.find((t) => t.path === st.path);
  const agentsIn = (path) => store.panes.filter((p) => p.cwd && p.cwd.replace(/\\/g, "/").startsWith(path.replace(/\\/g, "/")));
  const redraw = () => renderChanges(root, actions);

  const newWorktree = async () => {
    const task = await promptText("New task worktree", "", "Task name");
    if (!task) return;
    try { const r = await rpc("worktree.create", { repo: info.root, task, base: st.base }, machine); toast(`Created ${r.branch}`); st.path = r.path; redraw(); }
    catch (e) { errorToast(e); }
  };
  setTopExtra("changes", { right: h("button", { class: "btn", style: { marginLeft: "6px" }, onclick: newWorktree }, "+ New task worktree") });
  const doRemove = (force) => rpc("worktree.remove", force ? { path: current.path, force } : { path: current.path }, machine)
    .then(() => { st.path = null; st.confirm = false; redraw(); }).catch(errorToast);
  const removeBox = st.confirm && current && current !== mainTree ? h("div", { class: "warnbox", style: { margin: "6px" } },
    h("b", {}, `Remove “${agentsIn(current.path)[0]?.name || current.branch}”? `),
    current.changes ? `It has ${current.changes} uncommitted files, so herd won't delete it unless you force it.` : `${current.path} will be deleted.`,
    h("div", { class: "row", style: { marginTop: "8px" } },
      h("button", { class: "btn" + (current.changes ? " danger" : ""), onclick: () => doRemove(!!current.changes) }, current.changes ? "Remove anyway" : "Remove"),
      h("button", { class: "btn", onclick: () => { st.confirm = false; redraw(); } }, "Cancel"))) : null;

  const list = h("div", { class: "wtlist" }, ...trees.map((t, i) => treeRow(t, i, { path: st.path, agent: i ? agentsIn(t.path)[0] : null,
    onpick: () => { st.path = t.path; st.file = null; st.confirm = false; redraw(); } })),
  missing ? h("div", { style: { padding: "4px 10px" } },
    h("button", { class: "btn", title: "git worktree prune: forget worktrees whose folder is gone", onclick: async () => {
      try { await rpc("worktree.prune", { repo: info.root }, machine); toast("Cleaned up", `${missing} stale worktree${missing > 1 ? "s" : ""} removed from git's list`); redraw(); }
      catch (e) { errorToast(e); }
    } }, `Clean up ${missing} deleted`)) : null,
  current && current !== mainTree ? h("div", { class: "row", style: { padding: "6px 10px", flexWrap: "wrap" } },
    h("button", { class: "btn", onclick: () => actions.newAgent({ cwd: current.path, machine }) }, "Agent here"),
    h("button", { class: "btn danger", onclick: () => { st.confirm = true; redraw(); } }, "Remove")) : null,
  h("span", { class: "grow" }), removeBox);

  const files = cached ? cached.files : await rpc("worktree.changes", { path: st.path, base: st.base }, machine).catch(() => []);
  st.cache = { spaceId: space.id, path: st.path, info, trees, files };
  if (!st.file && files.length) st.file = files[0].path;
  const diffBox = h("div", { class: "grow", style: { overflow: "auto", padding: "10px 0" } });
  const fileList = h("div", { class: "cfiles" },
    ...files.map((f) => h("button", { class: "cf" + (f.path === st.file ? " on" : ""), onclick: () => { st.file = f.path; renderChanges(root, actions, true); } },
      h("span", { class: "cs " + (f.status || "M") }, f.status || "M"), h("span", { class: "mono grow trunc" }, f.path),
      h("span", { class: "add mono" }, `+${f.added}`), f.removed ? h("span", { class: "rem mono" }, `-${f.removed}`) : null)),
    files.length ? null : h("div", { class: "meta", style: { padding: "8px" } }, "No changes vs " + st.base));
  if (st.file) rpc("worktree.diff", { path: st.path, base: st.base, file: st.file }, machine)
    .then((r) => diffBox.replaceChildren(diffEl(r.diff))).catch((e) => diffBox.replaceChildren(h("div", { class: "errtext" }, e.message)));

  const act = (label, fn, pri) => h("button", { class: "btn" + (pri ? " pri" : ""), onclick: async () => {
    try { const r = await fn(); if (r?.output) toast(label, r.output.slice(0, 200)); redraw(); } catch (e) { errorToast(e); }
  } }, label);
  const baseIn = h("input", { class: "in mono basein", value: st.base, "aria-label": "Compare against",
    onchange: () => { st.base = baseIn.value.trim() || "main"; redraw(); } });
  root.replaceChildren(h("div", { class: "vsplit" },
    h("div", { class: "panel cwt", style: { width: "300px", flex: "none", padding: "6px" } }, list),
    h("div", { class: "panel focus grow" },
      h("div", { class: "ph", style: { flexWrap: "wrap", height: "auto", minHeight: "42px" } },
        h("span", { class: "mono", style: { color: "var(--accent)" } }, current?.branch || ""), h("span", { class: "meta" }, "vs"), baseIn,
        h("span", { class: "grow" }),
        act("Commit…", async () => { const m = await promptText("Commit message", "", "Message"); return m ? rpc("git.commit", { path: st.path, message: m }, machine) : null; }),
        act(`Rebase on ${st.base}`, () => rpc("git.rebase", { path: st.path, base: st.base }, machine)),
        act("Push & open PR", async () => { await rpc("git.push", { path: st.path }, machine); return rpc("git.pr", { path: st.path }, machine); }, true)),
      h("div", { class: "csplit", style: { display: "flex", flex: "1", minHeight: "0" } }, fileList, diffBox))));
}
