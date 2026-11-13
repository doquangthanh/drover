// Command palette (Ctrl+B :) — fuzzy list of every action.
import { h, icon } from "./dom.js";
import { openModal, closeModal } from "./modal.js";

export function openPalette(actions) {
  const commands = [
    ["Create", "New agent…", "newAgent", "Ctrl B c", "plus"],
    ["Create", "New agent in a fresh worktree…", "newAgentWorktree", "Ctrl B C", "branch"],
    ["Create", "New tab", "newTab", "Ctrl B t", "plus"],
    ["Create", "New space from folder…", "newSpace", "Ctrl B S", "folder"],
    ["Agents", "Jump to next agent that needs you", "nextBlocked", "Ctrl B n", "inbox"],
    ["Agents", "Jump to next finished agent", "nextDone", "Ctrl B N", "inbox"],
    ["Agents", "Send prompt to several agents…", "broadcast", "Ctrl B B", "up"],
    ["Agents", "Restart agent and resume session", "restart", "Ctrl B r", "restart"],
    ["Agents", "Send Esc to agent", "sendEsc", "Ctrl B e", "close"],
    ["Agents", "Rename pane", "rename", "Ctrl B ,", "keyboard"],
    ["Agents", "Agent tree", "tree", "Ctrl B o", "tree"],
    ["Layout", "Split right", "splitRight", "Ctrl B %", "split"],
    ["Layout", "Split down", "splitDown", 'Ctrl B "', "splitdown"],
    ["Layout", "Zoom pane", "zoom", "Ctrl B z", "zoom"],
    ["Layout", "Find in scrollback", "find", "Ctrl B [", "search"],
    ["Layout", "Close pane", "closePane", "Ctrl B x", "close"],
    ["Layout", "Toggle sidebar", "toggleSidebar", "Ctrl B b", "sidebar"],
    ["Go to", "Jump to a terminal", "search", "Ctrl B /", "search"],
    ["Go to", "Inbox", "inbox", "Ctrl B i", "inbox"],
    ["Go to", "Changes and worktrees", "changes", "Ctrl B w", "branch"],
    ["Go to", "Machines", "machines", "Ctrl B m", "server"],
    ["Go to", "Settings", "settings", "Ctrl B .", "gear"],
    ["Go to", "herd-server", "server", "Ctrl B D", "server"],
    ["Go to", "Keyboard shortcuts", "help", "Ctrl B ?", "keyboard"],
    ["System", "Send a test notification", "testNotify", "", "inbox"],
  ];
  let selected = 0;
  let shown = commands;
  const list = h("div", { class: "list" });
  const input = h("input", { class: "qin", placeholder: "Type a command", "aria-label": "Command", autofocus: true });

  const run = (cmd) => { closeModal(); setTimeout(() => actions[cmd[2]]?.({}), 0); };
  const render = () => {
    const q = input.value.toLowerCase().trim();
    shown = commands.filter((c) => !q || c[1].toLowerCase().includes(q) || c[0].toLowerCase().includes(q));
    selected = Math.min(selected, Math.max(0, shown.length - 1));
    const rows = [];
    let group = "";
    shown.forEach((c, i) => {
      if (c[0] !== group) { group = c[0]; rows.push(h("div", { class: "sec" }, group)); }
      rows.push(h("button", { class: "it" + (i === selected ? " on" : ""), onclick: () => run(c) },
        icon(c[4]), h("span", { class: "lb" }, c[1]), c[3] ? h("span", { class: "k" }, c[3]) : null));
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
  openModal({
    label: "Command palette",
    head: h("div", { class: "mhead" }, icon("up"), input, h("span", { class: "k" }, "Esc")),
    body: list,
  });
  list.after(h("div", { class: "hint" }, "↑↓ move", "↵ run", h("span", { class: "grow" }), `${commands.length} commands`));
  render();
}
