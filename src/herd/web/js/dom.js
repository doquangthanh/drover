// Tiny DOM helpers, icons and shared status atoms.

/** replaceChildren that skips null/false (plain replaceChildren would print "null"). */
export function fill(el, ...kids) {
  el.replaceChildren(...kids.flat(Infinity).filter((k) => k != null && k !== false));
}

/** "branch main ●2 ↑1" for a space that is a git repo (branch, uncommitted files, unpushed commits), else null. */
export function branchChip(space, onclick) {
  if (!space || !space.branch) return null;
  const bits = [icon("branch"), h("span", { class: "gb-name" }, space.branch)];
  if (space.dirty) bits.push(h("span", { class: "gb-dirty", title: `${space.dirty} uncommitted file${space.dirty > 1 ? "s" : ""}` }, `●${space.dirty}`));
  if (space.ahead) bits.push(h("span", { class: "gb-ahead", title: `${space.ahead} commit${space.ahead > 1 ? "s" : ""} not pushed` }, `↑${space.ahead}`));
  return h(onclick ? "button" : "span", { class: "gb", title: `Git branch ${space.branch}`, onclick }, ...bits);
}

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "html") el.innerHTML = v; // only used with trusted, static icon markup
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const PATHS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/>',
  server: '<rect x="3" y="4" width="18" height="7" rx="1.5"/><rect x="3" y="13" width="18" height="7" rx="1.5"/>',
  layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
  inbox: '<path d="M3 13h5l2 3h4l2-3h5"/><path d="M5 5h14l2 8v6H3v-6z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  folder: '<path d="M3 7h6l2 2h10v10H3z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  split: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 4v16"/>',
  splitdown: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 12h18"/>',
  zoom: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  tree: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="12" r="2"/><path d="M6 8v8M8 6h4a4 4 0 0 1 4 4v0"/>',
  branch: '<circle cx="6" cy="6" r="2"/><circle cx="6" cy="18" r="2"/><circle cx="18" cy="8" r="2"/><path d="M6 8v8M18 10c0 4-6 3-12 6"/>',
  restart: '<path d="M4 12a8 8 0 1 0 3-6.2M4 4v4h4"/>',
  back: '<path d="M15 6l-6 6 6 6"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  more: '<path d="M5 12h.01M12 12h.01M19 12h.01" stroke-width="3"/>',
  chevron: '<path d="M9 6l6 6-6 6"/>',
  tab: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18"/>',
  send: '<path d="M4 12h16M14 6l6 6-6 6"/>',
  home: '<path d="M3 11l9-7 9 7v9H3z"/>',
  keyboard: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
};

export function icon(name, cls = "i") {
  const span = document.createElement("span");
  span.style.display = "inline-flex";
  span.innerHTML = `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name] || ""}</svg>`;
  return span;
}

const AV_COLORS = ["#24877b", "#b9602f", "#4e7fe0", "#7a5fd6", "#2f8a4a", "#b2456b", "#8a7a2b", "#3d7f99"];
export function spaceAvatar(space) {
  const letter = (space?.name || "?").replace(/[^A-Za-z0-9]/g, "").charAt(0).toUpperCase() || "?";
  return h("span", { class: "av", style: { background: AV_COLORS[(space?.color || 0) % 8] } }, letter);
}

const KIND = {
  claude: ["C", "#d97757"], codex: ["X", "#5b8def"], gemini: ["G", "#8f7ce0"], opencode: ["O", "#a6bd91"],
  shell: ["$", "#3a3c40", "#d2d4d9"],
};
export function kindIcon(kind) {
  const [letter, bg, fg] = KIND[kind] || [String(kind || "?").charAt(0).toUpperCase(), "#818793"];
  return h("span", { class: "ic", style: { background: bg, color: fg || "#101114" }, title: kind }, letter);
}

export function stateMark(pane) {
  switch (pane.state) {
    case "blocked": return h("span", { class: "pill blocked" }, "Needs you");
    case "working": return h("span", { class: "spin", title: "working" });
    case "done": return h("span", { class: "dot done", title: "done" });
    case "exited": return h("span", { class: "pill bad" }, pane.exit_code ? `exit ${pane.exit_code}` : "exited");
    default: return h("span", { class: "ring", title: pane.state });
  }
}

export function ago(ts) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return s < 5 ? "<1m" : `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export function shortPath(path) {
  if (!path) return "";
  const parts = path.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.length > 3 ? "…/" + parts.slice(-2).join("/") : path;
}

/** Per-view extras for the desktop top bar: `meta` follows the title, `right` sits at the far end. Views set them; renderTopbar draws them. */
export const topExtra = { view: null, meta: null, right: null, paint: () => {} };
export function setTopExtra(view, parts) { Object.assign(topExtra, { view, meta: null, right: null }, parts); topExtra.paint(); }

export function toast(title, sub = "", onClick = null, lead = null) {
  const close = h("button", { class: "ibtn tx", "aria-label": "Dismiss", onclick: (e) => { e.stopPropagation(); el.remove(); } }, "×");
  const el = h("div", { class: "toast", role: "status" }, h("div", { class: "row" }, lead, h("b", { class: "grow" }, title), close),
    sub ? h("div", { class: "sub" }, sub) : null);
  el.addEventListener("click", () => { el.remove(); onClick && onClick(); });
  document.getElementById("toasts").append(el);
  setTimeout(() => el.remove(), 6000);
}

export function errorToast(err) { toast("Something went wrong", err?.message || String(err)); }
