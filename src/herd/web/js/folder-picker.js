// Folder chooser: native dialog in the desktop window for this computer; in-app browser otherwise.
import { conn } from "./connection.js";
import { store } from "./store.js";
import { h, fill, icon, errorToast } from "./dom.js";

export function hasNativePicker() {
  return !!(window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder);
}

/** Resolve to a path string or null. `machine` = null for this computer. */
export async function chooseFolder(machine, start = "") {
  if (!machine && hasNativePicker()) {
    try { return await window.pywebview.api.pick_folder(start || ""); } catch (e) { errorToast(e); }
  }
  return inAppPicker(machine, start);
}

function rpcFor(machine, method, params) {
  return conn.rpc(method, machine ? { ...params, machine } : params);
}

function inAppPicker(machine, start) {
  return new Promise((resolve) => {
    let current = null;
    let chosen = null;
    let filter = "";
    const crumb = h("span", { class: "mono trunc grow" });
    const list = h("div", { class: "list", style: { flex: "1" } });
    const footPath = h("span", { class: "mono meta trunc grow" });
    const note = h("div", { class: "meta", style: { padding: "8px 14px" } });
    const places = h("div", { style: { width: "200px", flex: "none", padding: "8px", borderRight: "1px solid var(--border)" } });
    const filterIn = h("input", { class: "in", style: { width: "220px", height: "30px" }, placeholder: "Filter folders",
      "aria-label": "Filter folders", oninput: () => { filter = filterIn.value.toLowerCase(); draw(); } });

    const finish = (value) => { scrim.remove(); resolve(value); };
    const load = async (path) => {
      try {
        current = await rpcFor(machine, "fs.list_dirs", { path });
        chosen = current.path;
        draw();
      } catch (e) { errorToast(e); }
    };
    const pick = async (entry) => {
      chosen = entry.path;
      footPath.textContent = (machine ? machine + ":" : "") + chosen;
      draw();
      try {
        const info = await rpcFor(machine, "git.info", { path: entry.path });
        note.textContent = info.is_repo ? `${entry.name} is a git repo on ${info.branch}` +
          (info.dirty ? ` with ${info.dirty} uncommitted files.` : ".") : "Not a git repo.";
      } catch { note.textContent = ""; }
    };
    const draw = () => {
      if (!current) return;
      crumb.textContent = current.path;
      footPath.textContent = (machine ? machine + ":" : "") + (chosen || current.path);
      const entries = current.entries.filter((e) => !filter || e.name.toLowerCase().includes(filter));
      list.replaceChildren(...entries.map((e) => h("button", {
        class: "fd" + (chosen === e.path ? " on" : ""), onclick: () => pick(e), ondblclick: () => load(e.path),
      }, icon("folder"), h("span", { class: "grow trunc" }, e.name), e.is_git ? h("span", { class: "pill ok" }, "git") : null,
      h("span", { class: "meta", style: { width: "90px", textAlign: "right" } },
        e.mtime ? new Date(e.mtime * 1000).toLocaleDateString() : ""))));
      if (!entries.length) list.append(h("div", { class: "sec" }, "No sub-folders"));
      const recent = [...new Set(store.spaces.filter((s) => (s.machine || null) === (machine || null) ||
        (!machine && (!s.machine || s.machine === "local"))).map((s) => s.cwd))].slice(0, 6);
      fill(places, h("div", { class: "sec" }, "Places"),
        ...current.roots.map((r) => h("button", { class: "nav", onclick: () => load(r) }, icon("folder"), " ", r)),
        recent.length ? h("div", { class: "sec" }, "Recent") : null,
        ...recent.map((r) => h("button", { class: "nav mono trunc", title: r, onclick: () => load(r) }, r.split(/[\\/]/).pop())));
    };
    const newFolder = async () => {
      const name = window.prompt("New folder name");
      if (!name) return;
      try { const r = await rpcFor(machine, "fs.mkdir", { parent: current.path, name }); await load(current.path); chosen = r.path; draw(); }
      catch (e) { errorToast(e); }
    };
    const modal = h("div", { class: "modal xwide", role: "dialog", "aria-modal": "true", "aria-label": "Choose a folder",
      style: { height: "640px" } },
    h("div", { class: "mhead" }, h("h2", {}, "Choose a folder"),
      h("span", { class: "meta" }, machine ? `on ${machine}` : "on this computer"), filterIn),
    h("div", { style: { flex: "1", minHeight: "0", display: "flex" } }, places,
      h("div", { style: { flex: "1", minWidth: "0", display: "flex", flexDirection: "column" } },
        h("div", { class: "row", style: { height: "40px", padding: "0 14px", borderBottom: "1px solid var(--border)" } },
          h("button", { class: "btn", "aria-label": "Up one level", onclick: () => current?.parent && load(current.parent) }, "↑"),
          crumb, h("button", { class: "btn", onclick: newFolder }, "+ New folder")),
        list, note)),
    h("div", { class: "mfoot" }, footPath, h("button", { class: "btn", onclick: () => finish(null) }, "Cancel"),
      h("button", { class: "btn pri", onclick: () => finish(chosen || current?.path || null) }, "Use this folder")));
    const scrim = h("div", { class: "scrim", style: { zIndex: 30 },
      onkeydown: (e) => { if (e.key === "Escape") { e.stopPropagation(); finish(null); } } }, modal);
    document.getElementById("overlay-root").append(scrim);
    load(start);
  });
}
