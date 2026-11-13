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

const base = (p) => String(p).replace(/[\\/]+$/, "").split(/[\\/]/).pop() || p;

function inAppPicker(machine, start) {
  return new Promise((resolve) => {
    let current = null;
    let chosen = null;
    let filter = "";
    const call = (method, params) => conn.rpc(method, machine ? { ...params, machine } : params);
    const crumb = h("span", { class: "crumb mono trunc grow" });
    const list = h("div", { class: "list", style: { flex: "1", padding: "6px 8px" } });
    const footPath = h("span", { class: "mono meta trunc grow" });
    const note = h("div", { class: "fp-note" });
    const places = h("div", { class: "fp-pl" });
    const filterIn = h("input", { placeholder: "Filter folders", "aria-label": "Filter folders",
      oninput: () => { filter = filterIn.value.toLowerCase(); draw(); } });
    const machines = ["", ...(store.raw.machines || []).filter((m) => m.status === "connected").map((m) => m.alias)];
    const machineSel = h("select", { class: "btn", "aria-label": "Machine", onchange: () => {
      machine = machineSel.value || null; chosen = null; note.replaceChildren(); load("");
    } }, ...machines.map((a) => h("option", { value: a }, a || "This computer")));
    machineSel.value = machine || "";
    const mname = h("span", { class: "meta" }, "on");

    const finish = (value) => { scrim.remove(); resolve(value); };
    const load = async (path) => {
      try { current = await call("fs.list_dirs", { path }); chosen = current.path; footNote(); draw(); }
      catch (e) { errorToast(e); }
    };
    const footNote = () => { footPath.textContent = (machine ? machine + ":" : "") + (chosen || current?.path || ""); };
    const pick = async (entry) => {
      chosen = entry.path; footNote(); draw();
      try {
        const info = await call("git.info", { path: entry.path });
        note.replaceChildren(...(info.is_repo ? [h("b", {}, entry.name), " is a git repo on ", h("span", { class: "mono ac", style: { color: "var(--accent)" } }, info.branch),
          info.dirty ? ` with ${info.dirty} uncommitted file${info.dirty > 1 ? "s" : ""}. A new worktree will branch from ` : ". A new worktree will branch from ",
          h("span", { class: "mono" }, info.branch), "."] : [h("b", {}, entry.name), " is not a git repo."]));
      } catch { note.replaceChildren(); }
    };
    const place = (label, path, ic, on) => h("button", { class: "pl" + (on ? " on" : ""), title: path, onclick: () => load(path) }, icon(ic), label);
    const draw = () => {
      if (!current) return;
      const cut = Math.max(current.path.lastIndexOf("/"), current.path.lastIndexOf("\\"));
      crumb.replaceChildren(current.path.slice(0, cut + 1) + (cut >= 0 && cut < current.path.length - 1 ? " " : ""), h("b", {}, current.path.slice(cut + 1)));
      const entries = current.entries.filter((e) => !filter || e.name.toLowerCase().includes(filter));
      list.replaceChildren(...entries.map((e) => h("button", {
        class: "fd" + (chosen === e.path ? " on" : ""), onclick: () => pick(e), ondblclick: () => load(e.path),
        style: e.name.startsWith(".") ? { color: "var(--dim)" } : null,
      }, icon("folder"), h("span", { class: "grow trunc" }, e.name), e.is_git ? h("span", { class: "gitpill" }, "git") : null,
      h("span", { class: "meta", style: { width: "90px", textAlign: "right" } }, e.name.startsWith(".") ? "hidden" : e.mtime ? ago(e.mtime) : ""))));
      if (!entries.length) list.append(h("div", { class: "sec" }, "No sub-folders"));
      const recent = [...new Set(store.spaces.filter((s) => (s.machine && s.machine !== "local" ? s.machine : null) === (machine || null))
        .map((s) => s.cwd))].slice(0, 6);
      const repos = current.entries.filter((e) => e.is_git).slice(0, 6);
      fill(places, h("div", { class: "meta" }, "Places"),
        ...current.roots.map((r, i) => place(i ? base(r) : "Home", r, i ? "folder" : "home", r === current.path)),
        recent.length ? h("div", { class: "meta", style: { paddingTop: "12px" } }, `Recent on ${machine || "this computer"}`) : null,
        ...recent.map((r) => h("button", { class: "pl", title: r, onclick: () => load(r) }, h("span", { class: "mono trunc" }, r))),
        repos.length ? h("div", { class: "meta", style: { paddingTop: "12px" } }, "Git repos found") : null,
        ...repos.map((e) => h("button", { class: "pl", onclick: () => pick(e) }, h("span", { class: "grow trunc" }, e.name), h("span", { class: "gitpill" }, "git"))));
    };
    const newFolder = async () => {
      const name = window.prompt("New folder name"); // not promptText: that would close the dialog underneath
      if (!name) return;
      try { const r = await call("fs.mkdir", { parent: current.path, name }); await load(current.path); chosen = r.path; footNote(); draw(); }
      catch (e) { errorToast(e); }
    };
    const modal = h("div", { class: "modal fp", role: "dialog", "aria-modal": "true", "aria-label": "Choose a folder" },
      h("div", { class: "mhead" }, h("h2", {}, "Choose a folder"), mname, machineSel, h("span", { class: "grow" }),
        h("label", { class: "fq" }, icon("search"), filterIn)),
      h("div", { class: "fp-body" }, places,
        h("div", { class: "fp-main" },
          h("div", { class: "fp-bar" },
            h("button", { class: "btn", "aria-label": "Up one level", style: { padding: "0 8px" }, onclick: () => current?.parent && load(current.parent) }, "↑"),
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

function ago(ts) {
  const d = Math.floor((Date.now() / 1000 - ts) / 86400);
  if (d < 1) return "today";
  if (d < 7) return d === 1 ? "yesterday" : `${d} days ago`;
  if (d < 30) return `${Math.floor(d / 7)} week${d >= 14 ? "s" : ""} ago`;
  return `${Math.floor(d / 30)} month${d >= 60 ? "s" : ""} ago`;
}
