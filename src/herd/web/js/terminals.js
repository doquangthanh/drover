// One xterm.js instance per pane, kept alive across re-renders (the element is moved, not rebuilt).
import { conn } from "./connection.js";
import { handleKey } from "./keys.js";
import { onThemeChange, termOptions, termTheme } from "./theme.js";

const terms = new Map();
onThemeChange(() => { for (const { term } of terms.values()) term.options.theme = termTheme(); });

export function getTerminal(paneId) {
  let entry = terms.get(paneId);
  if (entry) return entry;
  const el = document.createElement("div");
  el.className = "term";
  const term = new Terminal({
    fontFamily: '"JetBrains Mono", ui-monospace, Consolas, monospace', fontSize: matchMedia("(max-width: 760px)").matches ? 12 : 13, lineHeight: 1.15,
    ...termOptions(), scrollback: 5000, allowProposedApi: true, macOptionIsMeta: true,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  try { term.loadAddon(new WebLinksAddon.WebLinksAddon()); } catch { /* optional */ }
  entry = { paneId, el, term, fit, opened: false, lastSize: "", resizeTimer: null };
  // xterm answers the shell's "who are you" query (Device Attributes) and ConPTY hands that answer to PowerShell as
  // typed text ("[?1;2c" on the prompt). The shell never needs it, so it is dropped.
  term.onData((data) => { if (!/^\x1b\[[?>][\d;]*c$/.test(data)) conn.input(paneId, data); });
  term.attachCustomKeyEventHandler((ev) => handleKey(ev, paneId));
  conn.attach(paneId, (data, isReplay) => {
    if (isReplay) term.reset();
    term.write(data);
  });
  new ResizeObserver(() => scheduleFit(entry)).observe(el);
  terms.set(paneId, entry);
  return entry;
}

/** GPU renderer: far smoother than the default DOM renderer. Falls back silently. */
function enableWebgl(entry) {
  if (typeof WebglAddon === "undefined") return;
  try {
    const gl = new WebglAddon.WebglAddon();
    gl.onContextLoss(() => gl.dispose()); // xterm falls back to the DOM renderer
    entry.term.loadAddon(gl);
  } catch { /* no WebGL available */ }
}

function scheduleFit(entry) {
  if (!entry.el.isConnected || entry.el.offsetWidth < 20 || entry.el.offsetHeight < 20) return;
  if (!entry.opened) {
    entry.term.open(entry.el);
    entry.opened = true;
    enableWebgl(entry);
  }
  clearTimeout(entry.resizeTimer);
  entry.resizeTimer = setTimeout(() => {
    try { entry.fit.fit(); } catch { return; }
    const size = `${entry.term.cols}x${entry.term.rows}`;
    if (size !== entry.lastSize) {
      entry.lastSize = size;
      conn.rpc("pane.resize", { pane: entry.paneId, cols: entry.term.cols, rows: entry.term.rows }).catch(() => {});
    }
  }, 60);
}

export function focusTerminal(paneId) {
  const entry = terms.get(paneId);
  if (entry && entry.opened) entry.term.focus();
}

export function disposeMissing(liveIds) {
  for (const [id, entry] of terms) {
    if (!liveIds.has(id)) {
      conn.detach(id);
      entry.term.dispose();
      entry.el.remove();
      terms.delete(id);
    }
  }
}

export function sendToPane(paneId, data) { conn.input(paneId, data); }

/** Find text in the scrollback; selects and scrolls to the match. Returns {index, total}. */
export function findInPane(paneId, query, fromEnd = true, step = 0) {
  const entry = terms.get(paneId);
  if (!entry || !query) return { index: 0, total: 0 };
  const buf = entry.term.buffer.active;
  const q = query.toLowerCase();
  const hits = [];
  for (let y = 0; y < buf.length; y++) {
    const line = buf.getLine(y)?.translateToString(true) || "";
    let x = line.toLowerCase().indexOf(q);
    while (x >= 0) { hits.push([x, y]); x = line.toLowerCase().indexOf(q, x + 1); }
  }
  if (!hits.length) { entry.term.clearSelection(); return { index: 0, total: 0 }; }
  entry.findIndex = entry.findQuery === query ? (entry.findIndex + step + hits.length) % hits.length
    : (fromEnd ? hits.length - 1 : 0);
  entry.findQuery = query;
  const [x, y] = hits[entry.findIndex];
  entry.term.select(x, y, query.length);
  entry.term.scrollToLine(Math.max(0, y - Math.floor(entry.term.rows / 2)));
  return { index: entry.findIndex + 1, total: hits.length };
}

export function copySelection(paneId) {
  const entry = terms.get(paneId);
  const text = entry?.term.getSelection();
  if (text) navigator.clipboard?.writeText(text).catch(() => {});
  return !!text;
}
