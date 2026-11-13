// Prefix-key shortcuts (default Ctrl+B, then a key). Everything else goes to the agent.
import { store } from "./store.js";

export const SHORTCUTS = [
  ["Agents", [["c", "New agent", "newAgent"], ["C", "New agent + worktree", "newAgentWorktree"],
    ["n", "Next that needs you", "nextBlocked"], ["N", "Next that's done", "nextDone"],
    ["a", "Answer prompt (then 1–3)", "answer"], ["e", "Send Esc", "sendEsc"],
    ["B", "Send to selected", "broadcast"], ["r", "Restart + resume", "restart"], ["o", "Agent tree", "tree"]]],
  ["Panes", [["%", "Split right", "splitRight"], ['"', "Split down", "splitDown"],
    ["ArrowLeft", "Focus left", "focusPrev"], ["ArrowRight", "Focus right", "focusNext"],
    ["z", "Zoom", "zoom"], ["[", "Find / scroll", "find"], [",", "Rename", "rename"], ["x", "Close pane", "closePane"]]],
  ["Tabs & spaces", [["t", "New tab", "newTab"], ["1", "Go to tab 1–9", "gotoTab"], ["Tab", "Next tab", "nextTab"],
    ["s", "Switch space", "switchSpace"], ["S", "New space", "newSpace"], ["b", "Toggle sidebar", "toggleSidebar"]]],
  ["herd", [[":", "Command palette", "palette"], ["/", "Jump to a terminal", "search"], ["i", "Inbox", "inbox"],
    ["w", "Changes / worktrees", "changes"], ["m", "Machines", "machines"], [".", "Settings", "settings"],
    ["D", "Server", "server"], ["?", "This list", "help"]]],
];

const BY_KEY = new Map();
for (const [, items] of SHORTCUTS) for (const [key, , action] of items) BY_KEY.set(key, action);
for (let i = 2; i <= 9; i++) BY_KEY.set(String(i), "gotoTab");

let actions = {};
let prefixKey = { ctrl: true, key: "b" };
let answerMode = false;

export function registerActions(map) { actions = map; }

export function setPrefix(spec) {
  const m = /^C-(.)$/i.exec(spec || "C-b");
  prefixKey = { ctrl: true, key: (m ? m[1] : "b").toLowerCase() };
}

function setPrefixUi(on) {
  store.ui.prefix = on;
  store.emit();
}

/** Returns false when the key was consumed (xterm convention). */
export function handleKey(ev, paneId = null) {
  if (ev.type !== "keydown") return true;
  if (store.ui.prefix) {
    if (["Control", "Shift", "Alt", "Meta"].includes(ev.key)) return false;
    ev.preventDefault();
    setPrefixUi(false);
    if (ev.ctrlKey && ev.key.toLowerCase() === prefixKey.key && paneId) {
      actions.sendRaw?.(paneId, String.fromCharCode(prefixKey.key.charCodeAt(0) - 96));
      return false;
    }
    if (ev.key === "a") { answerMode = true; return false; }
    const action = BY_KEY.get(ev.key);
    if (action && actions[action]) actions[action]({ key: ev.key, paneId });
    return false;
  }
  if (answerMode) {
    answerMode = false;
    if (/^[1-9]$/.test(ev.key) && paneId) { ev.preventDefault(); actions.sendRaw?.(paneId, ev.key); return false; }
  }
  if (ev.ctrlKey && !ev.shiftKey && !ev.altKey && ev.key.toLowerCase() === prefixKey.key) {
    ev.preventDefault();
    setPrefixUi(true);
    return false;
  }
  return true;
}

// Prefix also works when focus is outside a terminal (sidebar, views).
window.addEventListener("keydown", (ev) => {
  const t = ev.target;
  if (t && t.closest && t.closest(".xterm")) return; // xterm calls handleKey itself
  if (t && /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) && !store.ui.prefix && !ev.ctrlKey) return;
  if (handleKey(ev, store.ui.focusedPane || null) === false) ev.stopPropagation();
}, true);
