// Command palette (Ctrl+B :) — fuzzy list of every action.
import { h, icon } from "./dom.js";
import { openModal, closeModal } from "./modal.js";
import { THEMES, setTheme } from "./theme.js";
import { ICON_SETS, setIconSet } from "./file-icons.js";

export function openPalette(actions) {
  const commands = [
    ["Create", "New agent…", "newAgent", "Ctrl B c", "plus"],
    ["Create", "New agent in a fresh worktree…", "newAgentWorktree", "Ctrl B C", "branch"],
    ["Create", "New tab", "newTab", "Ctrl B t", "tab"],
    ["Create", "New space from folder…", "newSpace", "Ctrl B S", "folder"],
    ["Create", "New space on machine…", "newSpaceOn", "", "server"],
    ["Agents", "Jump to next agent that needs you", "nextBlocked", "Ctrl B n", "dot"],
    ["Agents", "Jump to next finished agent", "nextDone", "Ctrl B N", "inbox"],
    ["Agents", "Send prompt to selected agents…", "broadcast", "Ctrl B B", "send"],
    ["Agents", "Restart agent and resume session", "restart", "Ctrl B r", "restart"],
    ["Agents", "Send Esc to agent", "sendEsc", "Ctrl B e", "close"],
    ["Agents", "Rename pane", "rename", "Ctrl B ,", "keyboard"],
    ["Agents", "Agent tree", "tree", "Ctrl B o", "tree"],
    ["Layout", "Split right", "splitRight", "Ctrl B %", "split"],
    ["Layout", "Split down", "splitDown", 'Ctrl B "', "splitdown"],
    ["Layout", "Zoom pane", "zoom", "Ctrl B z", "zoom"],
    ["Layout", "Find in scrollback", "find", "Ctrl B [", "search"],
    ["Layout", "Close pane", "closePane", "Ctrl B x", "close"],
    ["Layout", "Close current space…", "closeSpace", "", "close"],
    ["Layout", "Toggle sidebar", "toggleSidebar", "Ctrl B b", "sidebar"],
    ["Go to", "Jump to a terminal", "search", "Ctrl B /", "search"],
    ["Go to", "Inbox", "inbox", "Ctrl B i", "inbox"],
    ["Go to", "Files: tree, code and changed files", "files", "Ctrl B f", "folder"],
    ["Go to", "Changes and worktrees", "changes", "Ctrl B w", "branch"],
    ["Go to", "Machines", "machines", "Ctrl B m", "server"],
    ["Go to", "Settings", "settings", "Ctrl B .", "gear"],
    ["Go to", "herd-server", "server", "Ctrl B D", "server"],
    ["Go to", "Keyboard shortcuts", "help", "Ctrl B ?", "keyboard"],
    ["System", "Send a test notification", "testNotify", "", "inbox"],
    ...THEMES.map(([id, label]) => ["Theme", `Theme: ${label}`, `theme:${id}`, "", "gear"]),
    ...ICON_SETS.map(([id, label]) => ["Theme", `File icons: ${label}`, `icons:${id}`, "", "folder"]),
  ];
  let selected = 0;
  let shown = commands;
  const list = h("div", { class: "list" });
  const input = h("input", { class: "qin", placeholder: "Type a command", "aria-label": "Command", autofocus: true });

  const run = (cmd) => {
    if (cmd[2] === "newSpaceOn") { closeModal(); setTimeout(() => actions.show("machines"), 0); return; }
    closeModal();
    if (cmd[2].startsWith("theme:")) setTheme(cmd[2].slice(6));
    else if (cmd[2].startsWith("icons:")) setIconSet(cmd[2].slice(6));
    else setTimeout(() => actions[cmd[2]]?.({}), 0);
  };
  const render = () => {
    const q = input.value.toLowerCase().trim();
    shown = commands.filter((c) => !q || c[1].toLowerCase().includes(q) || c[0].toLowerCase().includes(q));
    selected = Math.min(selected, Math.max(0, shown.length - 1));
    const rows = [];
    let group = "";
    shown.forEach((c, i) => {
      if (c[0] !== group) { group = c[0]; rows.push(h("div", { class: "sec" }, group)); }
      rows.push(h("button", { class: "it" + (i === selected ? " on" : ""), onclick: () => run(c) },
        c[4] === "dot" ? h("span", { class: "dot blocked" }) : icon(c[4]), h("span", { class: "lb" }, c[1]),
        ...(c[3] ? [h("span", { class: "k" }, c[3].slice(0, 6)), h("span", { class: "k" }, c[3].slice(7))] : [])));
    count.textContent = `${shown.length} of ${commands.length} commands`;
    });
    list.replaceChildren(...rows);
    list.querySelector(".it.on")?.scrollIntoView({ block: "nearest" });
  };
  input.addEventListener("input", () => { selected = 0; render(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { selected = Math.min(selected + 1, shown.length - 1); render(); e.preventDefault(); }
    if (e.key === "ArrowUp") { selected = Math.max(selected - 1, 0); render(); e.preventDefault(); }
    if (e.key === "Enter" && shown[selected]) run(shown[selected]);
  });
  const count = h("span", {});
  openModal({
    label: "Command palette", size: "pal",
    head: h("div", { class: "mhead" }, icon("chevron"), input, h("span", { class: "k" }, "Esc")),
    body: list,
  });
  list.after(h("div", { class: "hint" }, h("span", {}, "↑↓ move"), h("span", {}, "↵ run"), h("span", { class: "grow" }), count));
  render();
}
