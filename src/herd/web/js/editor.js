// Code editor (Ace, vendored). One editor instance for the whole app; every open file keeps its own session,
// so switching files keeps undo history, cursor and unsaved edits (like tabs in an IDE).
import { activeTheme, onThemeChange } from "./theme.js";

const MODE_BY_EXT = {
  py: "python", js: "javascript", mjs: "javascript", cjs: "javascript", jsx: "jsx", ts: "typescript", tsx: "tsx",
  json: "json", html: "html", htm: "html", css: "css", scss: "scss", md: "markdown", markdown: "markdown",
  yml: "yaml", yaml: "yaml", toml: "toml", sh: "sh", bash: "sh", zsh: "sh", ps1: "powershell", bat: "batchfile",
  cmd: "batchfile", sql: "sql", xml: "xml", svg: "svg", java: "java", c: "c_cpp", h: "c_cpp", cpp: "c_cpp",
  hpp: "c_cpp", cs: "csharp", go: "golang", rs: "rust", php: "php", rb: "ruby", ini: "ini", cfg: "ini",
  diff: "diff", patch: "diff", kt: "kotlin", swift: "swift", lua: "lua",
};
const THEME_FILE = { dark: "tomorrow_night", midnight: "tomorrow_night_blue", light: "github" };

export function modeFor(path) {
  const name = path.split("/").pop().toLowerCase();
  if (name === "dockerfile") return "dockerfile";
  return MODE_BY_EXT[name.includes(".") ? name.split(".").pop() : ""] || "text";
}

let ed = null;
let dirtyCb = null;
const sessions = new Map(); // key -> { session, mtime, path }

/** `fn` runs after every edit in any open document. */
export function onEdit(fn) { dirtyCb = fn; }

function create() {
  const el = document.createElement("div");
  el.className = "fcode";
  const ace = window.ace;
  ace.config.set("basePath", "/static/vendor/ace");
  const editor = ace.edit(el, {
    fontFamily: '"JetBrains Mono", ui-monospace, Consolas, monospace', fontSize: 13, showPrintMargin: false,
    scrollPastEnd: 0.25, highlightActiveLine: true, tabSize: 4, useSoftTabs: true,
  });
  editor.renderer.setScrollMargin(6, 0);
  const applyTheme = () => editor.setTheme(`ace/theme/${THEME_FILE[activeTheme()] || THEME_FILE.dark}`);
  applyTheme();
  onThemeChange(applyTheme);
  return { el, editor, onSave: null };
}

/** The shared editor element (attach it anywhere) and its Ace instance. */
export function getEditor() {
  if (!ed) ed = create();
  return ed;
}

/** Open (or switch to) a document. Existing sessions keep their unsaved edits. */
export function openDoc(key, path, text, mtime, editable) {
  const { editor } = getEditor();
  let doc = sessions.get(key);
  if (!doc) {
    const session = window.ace.createEditSession(text, `ace/mode/${modeFor(path)}`);
    session.setUseWorker(false); // no lint workers: keeps it offline and light
    session.setNewLineMode("auto"); // keep the file's own CRLF / LF when saving
    session.getUndoManager().markClean();
    session.on("change", () => dirtyCb?.());
    doc = { session, mtime, path };
    sessions.set(key, doc);
  }
  doc.mtime = doc.mtime ?? mtime;
  editor.setSession(doc.session);
  editor.setReadOnly(!editable);
  doc.editable = editable;
  return doc;
}

export const getDoc = (key) => sessions.get(key);
export const isDirty = (key) => { const d = sessions.get(key); return !!d && !d.session.getUndoManager().isClean(); };
export const dirtyKeys = () => [...sessions.keys()].filter(isDirty);
export const forgetDoc = (key) => sessions.delete(key);

/** Replace a clean document's text with what is on disk now (keeps the scroll position). */
export function reloadDoc(key, text, mtime) {
  const doc = sessions.get(key);
  if (!doc) return;
  const top = doc.session.getScrollTop();
  doc.session.setValue(text);
  doc.session.getUndoManager().reset();
  doc.session.getUndoManager().markClean();
  doc.session.setScrollTop(top);
  doc.mtime = mtime;
}

export function markSaved(key, mtime) {
  const doc = sessions.get(key);
  if (!doc) return;
  doc.mtime = mtime;
  doc.session.getUndoManager().markClean();
}

/** Ctrl/Cmd+S inside the editor. */
export function onSave(fn) {
  getEditor().editor.commands.addCommand({ name: "herdSave", bindKey: { win: "Ctrl-S", mac: "Command-S" }, exec: fn });
}

/** Call after the editor element was attached or resized. */
export function layout() {
  requestAnimationFrame(() => ed?.editor.resize(true));
}

window.addEventListener("beforeunload", (e) => { if (dirtyKeys().length) { e.preventDefault(); e.returnValue = ""; } });
