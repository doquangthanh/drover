// Files: folder tree of the current space, a code editor (Ace), and which files changed (with their diff).
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, fill, toast, errorToast } from "../dom.js";
import { confirmBox, promptText } from "../modal.js";
import { diffEl } from "./changes-view.js";
import { fileIcon, onIconSetChange } from "../file-icons.js";
import { getEditor, openDoc, getDoc, isDirty, reloadDoc, markSaved, onSave, onEdit, layout } from "../editor.js";

const st = { spaceId: null, dirs: new Map(), open: new Set(), status: {}, isRepo: false, file: null, tab: "file",
  only: false, content: null, diff: null, stale: false, timer: null, redraw: null, space: null, wasDirty: false, stage: "tree" };
const CHANGED = new Set(["M", "A", "D", "R"]);
const BADGE = { M: "M", A: "A", D: "D", R: "R", "?": "U" };

const machineOf = (space) => (space.machine && space.machine !== "local" ? space.machine : null);
const call = (space, method, params = {}) => conn.rpc(method, { ...params, ...(machineOf(space) ? { machine: machineOf(space) } : {}) });
const keyOf = (path) => `${st.space.id}:${path}`;

async function loadDir(space, path) { st.dirs.set(path, (await call(space, "files.list", { space: space.id, path })).entries); }
async function loadStatus(space) { const r = await call(space, "files.status", { space: space.id }); st.isRepo = r.is_repo; st.status = r.files; }
async function loadContent(space) {
  try { st.content = await call(space, "files.read", { space: space.id, path: st.file }); } catch (e) { st.content = { error: e.message }; }
  syncDoc();
}
async function loadDiff(space) {
  st.diff = null;
  if (!CHANGED.has(st.status[st.file])) return;
  try { st.diff = await call(space, "worktree.diff", { path: space.cwd, base: "HEAD", file: st.file }); } catch (e) { st.diff = { diff: "", error: e.message }; }
}

/** Disk vs editor: a clean document follows the disk; one with unsaved edits is flagged instead of overwritten. */
function syncDoc() {
  const c = st.content, doc = c && !c.error && !c.binary ? getDoc(keyOf(st.file)) : null;
  st.stale = false;
  if (!doc || c.mtime_us === doc.mtime) return;
  if (isDirty(keyOf(st.file))) st.stale = true; else reloadDoc(keyOf(st.file), c.text, c.mtime_us);
}

const phone = () => matchMedia("(max-width: 760px)").matches; // phones show the tree OR the file, never both

async function openFile(space, path) {
  st.file = path; st.content = null; st.diff = null; st.stale = false; st.stage = "file";
  await Promise.all([loadContent(space), loadDiff(space)]);
  st.tab = st.content?.error && CHANGED.has(st.status[path]) ? "diff" : "file"; // a deleted file can only show its diff
}

async function save(space, force = false) {
  const path = st.file, doc = path && getDoc(keyOf(path));
  if (!doc || !doc.editable) return;
  try {
    const r = await call(space, "files.write", { space: space.id, path, text: doc.session.getValue(), base_mtime_us: doc.mtime, force });
    markSaved(keyOf(path), r.mtime_us);
    toast("Saved", path);
    await refresh(space, true);
  } catch (e) {
    if (!/changed on disk/.test(e.message)) { errorToast(e); return; }
    if (await confirmBox("File changed on disk", "Something else (an agent?) changed this file after you opened it. Overwrite it with your version?", "Overwrite", true)) save(space, true);
  }
}

async function newFile(space) {
  const dir = st.file && st.file.includes("/") ? st.file.slice(0, st.file.lastIndexOf("/") + 1) : "";
  const path = (await promptText("New file", dir, "path inside this space, e.g. src/utils.py") || "").trim().replace(/^\/+/, "");
  if (!path) return;
  try {
    await call(space, "files.write", { space: space.id, path, text: "", create: true });
    for (let i = path.indexOf("/"); i > 0; i = path.indexOf("/", i + 1)) st.open.add(path.slice(0, i));
    await refresh(space, true);
    await openFile(space, path);
    st.redraw();
  } catch (e) { errorToast(e); }
}

const statusOf = (e) => (e.dir ? (st.status[e.path + "/"] ? "?" : null) : st.status[e.path] || null);
const dirChanged = (path) => Object.keys(st.status).some((k) => k.startsWith(path + "/"));
const badge = (s) => h("span", { class: `fb ${s === "?" ? "U" : s}` }, BADGE[s]);

function rows(path, depth, out) {
  for (const e of st.dirs.get(path) || []) {
    out.push([e, depth]);
    if (e.dir && st.open.has(e.path)) rows(e.path, depth + 1, out);
  }
  return out;
}

function fileRow(e, depth, space) {
  const s = statusOf(e), open = st.open.has(e.path);
  const onclick = async () => {
    if (e.dir) {
      if (open) st.open.delete(e.path); else { st.open.add(e.path); if (!st.dirs.has(e.path)) await loadDir(space, e.path).catch(() => {}); }
    } else await openFile(space, e.path);
    st.redraw();
  };
  return h("button", { class: "fileitem" + (e.path === st.file ? " on" : ""), style: { paddingLeft: `${10 + depth * 14}px` }, title: e.path, onclick },
    h("span", { class: "caret" }, e.dir ? (open ? "▾" : "▸") : ""), fileIcon(e.name, e.dir, open), h("span", { class: "mono grow trunc" }, e.name),
    !e.dir && isDirty(keyOf(e.path)) ? h("span", { class: "fdirty", title: "Unsaved changes" }, "●") : null,
    s ? badge(s) : (e.dir && dirChanged(e.path) ? h("span", { class: "fdot" }) : null));
}

function changedRow(path, status, space) {
  const dir = path.endsWith("/"), clean = dir ? path.slice(0, -1) : path;
  return h("button", { class: "fileitem" + (clean === st.file ? " on" : ""), title: clean, onclick: async () => {
    if (!dir) { await openFile(space, clean); st.redraw(); return; }
    st.only = false; // an untracked folder: jump into the full tree, open down to it
    let acc = "";
    for (const part of clean.split("/")) { acc = acc ? `${acc}/${part}` : part; st.open.add(acc); if (!st.dirs.has(acc)) await loadDir(space, acc).catch(() => {}); }
    st.redraw();
  } }, fileIcon(clean.split("/").pop(), dir), h("span", { class: "mono grow trunc" }, clean), badge(status));
}

function treePanel(space) {
  const changed = Object.entries(st.status).sort(([a], [b]) => a.localeCompare(b));
  const seg = (label, only) => h("button", { class: "seg" + (st.only === only ? " on" : ""), onclick: () => { st.only = only; st.redraw(); } }, label);
  const list = st.only ? changed.map(([p, s]) => changedRow(p, s, space)) : rows("", 0, []).map(([e, d]) => fileRow(e, d, space));
  const empty = st.only && !changed.length ? h("div", { class: "meta", style: { padding: "10px" } }, st.isRepo ? "No changes — working tree is clean." : "Not a git repository.") : null;
  return h("div", { class: "panel", style: { width: "320px", flex: "none" } },
    h("div", { class: "ph" }, h("b", { class: "trunc" }, space.name), h("span", { class: "grow" }), seg("All", false), seg(`Changed${changed.length ? ` ${changed.length}` : ""}`, true),
      h("button", { class: "btn", title: "New file", onclick: () => newFile(space) }, "+"),
      h("button", { class: "btn", title: "Reload", onclick: () => refresh(space, true) }, "↻")),
    h("div", { class: "pb-body ftree" }, ...list, empty));
}

function note(text, cls = "meta") { return h("div", { class: cls, style: { padding: "14px" } }, text); }

function editorPane() {
  const c = st.content;
  if (!c) return note("Loading…");
  if (c.error) return note(c.error, "errtext");
  if (c.binary) return note(`Binary file · ${(c.size / 1024).toFixed(1)} KB — not shown.`);
  const { el } = getEditor();
  openDoc(keyOf(st.file), st.file, c.text, c.mtime_us, c.editable);
  layout();
  return h("div", { class: "fedit" }, el,
    !c.editable ? h("div", { class: "warnbar" }, `Read-only: ${c.why_readonly}.`) : null);
}

function viewer(space) {
  if (!st.file) return h("div", { class: "panel grow" }, note("Pick a file on the left to read or edit it."));
  const changed = CHANGED.has(st.status[st.file]), key = keyOf(st.file), dirty = isDirty(key);
  const seg = (label, tab) => h("button", { class: "seg" + (st.tab === tab ? " on" : ""), onclick: () => { st.tab = tab; st.redraw(); } }, label);
  const body = st.tab === "diff" && changed
    ? (st.diff?.error ? note(st.diff.error, "errtext") : diffEl(st.diff?.diff)) : editorPane();
  const editable = st.tab === "file" && st.content && st.content.editable;
  return h("div", { class: "panel focus grow", style: { minWidth: "0" } },
    h("div", { class: "ph" }, h("button", { class: "btn mobile-only", "aria-label": "Back to files", onclick: () => { st.stage = "tree"; st.redraw(); } }, "‹"),
      fileIcon(st.file.split("/").pop()), h("span", { class: "mono trunc" }, st.file), dirty ? h("span", { class: "fdirty", title: "Unsaved changes" }, "●") : null, h("span", { class: "grow" }),
      st.stale ? h("span", { class: "meta", style: { color: "var(--blocked)" } }, "Changed on disk") : null,
      st.stale ? h("button", { class: "btn", title: "Discard your edits and load the disk version", onclick: () => {
        reloadDoc(key, st.content.text, st.content.mtime_us); st.stale = false; st.redraw(); } }, "Reload") : null,
      changed ? [seg("File", "file"), seg("Diff", "diff")] : null,
      editable ? h("button", { class: "btn pri", disabled: dirty ? null : true, title: "Save (Ctrl+S)", onclick: () => save(space) }, "Save") : null),
    h("div", { class: "fview", style: { flex: "1", minHeight: "0", overflow: st.tab === "file" ? "hidden" : "auto" } }, body));
}

function draw(root, space) {
  const ed = getEditor().editor, hadFocus = ed.isFocused();
  const keep = { tree: root.querySelector(".ftree")?.scrollTop, view: root.querySelector(".fview")?.scrollTop };
  const showFile = phone() && st.file && st.stage === "file";
  fill(root, h("div", { class: "vsplit" }, ...(phone() ? [showFile ? viewer(space) : treePanel(space)] : [treePanel(space), viewer(space)])));
  const tree = root.querySelector(".ftree"), view = root.querySelector(".fview");
  if (tree && keep.tree) tree.scrollTop = keep.tree;
  if (view && keep.view && st.tab === "diff") view.scrollTop = keep.view;
  if (hadFocus) ed.focus();
  st.wasDirty = !!st.file && isDirty(keyOf(st.file));
}

async function refresh(space, force = false) {
  const before = JSON.stringify(st.status), wasStale = st.stale;
  await loadStatus(space);
  let changed = force || before !== JSON.stringify(st.status);
  if (changed) await Promise.all([...st.dirs.keys()].map((p) => loadDir(space, p).catch(() => st.dirs.delete(p))));
  if (st.file) {
    await loadContent(space);
    if (CHANGED.has(st.status[st.file])) await loadDiff(space); else st.diff = null;
    changed ||= st.stale !== wasStale;
  }
  if (changed) st.redraw();
}

onIconSetChange(() => { if (st.redraw && store.ui.view === "files") st.redraw(); });

export async function renderFiles(root) {
  clearInterval(st.timer);
  const space = store.space(store.ui.spaceId);
  if (!space) { fill(root, h("div", { class: "view meta" }, "Open a space first.")); return; }
  if (st.spaceId !== space.id) Object.assign(st, { spaceId: space.id, dirs: new Map(), open: new Set(), file: null, content: null, diff: null, status: {}, stale: false });
  Object.assign(st, { space, redraw: () => draw(root, space) });
  if (!st.dirs.has("")) fill(root, h("div", { class: "view meta" }, "Loading files…"));
  try { await Promise.all([st.dirs.has("") ? null : loadDir(space, ""), loadStatus(space)]); }
  catch (e) { fill(root, h("div", { class: "view errtext" }, e.message)); return; }
  if (st.file) await loadContent(space);
  onSave(() => save(space));
  onEdit(() => { const d = !!st.file && isDirty(keyOf(st.file)); if (d !== st.wasDirty && root.isConnected) st.redraw(); });
  draw(root, space);
  // The agents are editing these files right now: look for changes every few seconds while this view is open.
  st.timer = setInterval(() => {
    if (!root.isConnected || store.ui.view !== "files") { clearInterval(st.timer); return; }
    if (!document.hidden) refresh(space).catch(() => {});
  }, 3000);
}
