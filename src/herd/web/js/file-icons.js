// File-tree icons. Choose a set in Settings (or `file_icons` in settings.toml):
//   material = Material Icon Theme (colourful, per file type / folder name)   badge = coloured text labels
//   line     = one-colour outline icons that follow the theme                 none  = just the folder arrows
// Precedence: this device's choice (localStorage) > settings.toml > "material".

export const ICON_SETS = [
  ["material", "Material", "Colourful icons per file type and folder name (like VS Code)"],
  ["badge", "Badges", "Small coloured labels: PY, JS, MD…"],
  ["line", "Line", "One colour, follows the theme"],
  ["none", "None", "Only the folder arrows"],
];
const KEY = "herd-file-icons";
const listeners = new Set();
let serverSet = "material";
let table = null; // Material lookup, loaded on first use
let loading = false;

const stored = () => { try { return localStorage.getItem(KEY); } catch { return null; } };
export function chosenIconSet() { const s = stored() || serverSet; return ICON_SETS.some(([id]) => id === s) ? s : "material"; }
export function onIconSetChange(fn) { listeners.add(fn); }
const notify = () => listeners.forEach((fn) => fn());

export function setIconSet(name) {
  try { localStorage.setItem(KEY, name); } catch { /* private mode: this session only */ }
  notify();
}
export function setServerIconSet(name) {
  if (typeof name === "string" && name !== serverSet) { serverSet = name; notify(); }
}

function loadTable() {
  if (table || loading) return;
  loading = true;
  fetch("/static/icons/material/map.json").then((r) => r.json()).then((t) => { table = t; notify(); }).catch(() => { loading = false; });
}

function materialName(name, dir, open) {
  const lower = name.toLowerCase();
  if (dir) {
    const closed = table.folders[lower] || table.folder;
    return open ? (table.openOf[closed] || table.folderOpen) : closed;
  }
  if (table.names[lower]) return table.names[lower];
  const parts = lower.split(".");
  for (let i = 1; i < parts.length; i++) { const hit = table.ext[parts.slice(i).join(".")]; if (hit) return hit; } // "a.test.ts" -> "test.ts" -> "ts"
  return table.file;
}

const svg = (body, cls = "fi") => {
  const s = document.createElement("span");
  s.className = cls;
  s.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
  return s;
};

const FILE = '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>';
const LINE = {
  folder: '<path d="M3 7h6l2 2h10v10H3z"/>', open: '<path d="M3 7h6l2 2h8v3"/><path d="M3 19l3-7h16l-3 7z"/>',
  code: FILE + '<path d="M10 13l-2 2 2 2M14 13l2 2-2 2"/>', text: FILE + '<path d="M9 12h6M9 15h6M9 18h4"/>',
  image: FILE + '<path d="M8 18l3-3 2 2 2-2 1 1"/>', data: FILE + '<path d="M9 13h6M9 17h6"/>', file: FILE,
};
const KIND = {
  code: "py js mjs cjs jsx ts tsx java c h cpp hpp cs go rs php rb kt swift lua sh bash ps1 bat sql html css scss xml svg",
  text: "md markdown txt rst log", image: "png jpg jpeg gif webp ico bmp", data: "json yaml yml toml ini cfg env lock csv",
};
const kindOf = (ext) => Object.keys(KIND).find((k) => KIND[k].split(" ").includes(ext)) || "file";

const BADGE_COLORS = { py: "#3572a5", js: "#c9a800", ts: "#3178c6", tsx: "#3178c6", jsx: "#c9a800", json: "#8a8f98", md: "#519aba",
  html: "#e34c26", css: "#563d7c", yml: "#cb171e", yaml: "#cb171e", toml: "#9c4221", sh: "#4eaa25", sql: "#e38c00", go: "#00add8", rs: "#b7410e" };
const PALETTE = ["#d97757", "#5b8def", "#8f7ce0", "#4cc48c", "#e0a030", "#d6578c", "#3fa7a7", "#7d8590"];

function badge(name) {
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  const label = (ext || name.slice(0, 2)).slice(0, 3).toUpperCase();
  let hash = 0;
  for (const ch of ext || name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const s = document.createElement("span");
  s.className = "fi fi-badge";
  s.textContent = label;
  s.style.background = BADGE_COLORS[ext] || PALETTE[hash % PALETTE.length];
  return s;
}

/** Icon element for a tree row, or null for the "none" set. `open` only matters for folders. */
export function fileIcon(name, dir = false, open = false, set = chosenIconSet()) {
  if (set === "none") return null;
  if (set === "material") {
    loadTable();
    if (!table) return svg(LINE[dir ? "folder" : "file"]); // brief placeholder while the lookup loads
    const img = document.createElement("img");
    img.className = "fi";
    img.alt = "";
    img.loading = "lazy";
    img.src = `/static/icons/material/${materialName(name, dir, open)}.svg`;
    return img;
  }
  if (set === "badge") return dir ? svg(LINE[open ? "open" : "folder"]) : badge(name);
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  return svg(dir ? LINE[open ? "open" : "folder"] : LINE[kindOf(ext)]);
}
