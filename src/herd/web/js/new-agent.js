// "New agent" dialog: agent kind, machine, folder (native or in-app picker), worktree, placement, first prompt.
import { conn } from "./connection.js";
import { store } from "./store.js";
import { h, kindIcon, icon, errorToast } from "./dom.js";
import { openModal, closeModal } from "./modal.js";
import { chooseFolder } from "./folder-picker.js";

const AGENTS = [["claude", "Claude Code", "claude"], ["codex", "Codex", "codex"], ["gemini", "Gemini", "gemini"],
  ["opencode", "opencode", "opencode"], ["shell", "Shell", ""], ["custom", "Custom…", null]];

export function openNewAgent(actions, opts = {}) {
  const focused = store.pane(store.ui.focusedPane);
  const space = store.space(store.ui.spaceId);
  const st = {
    kind: opts.kind || "claude", machine: opts.machine ?? (space?.machine && space.machine !== "local" ? space.machine : null),
    cwd: opts.cwd || space?.cwd || focused?.cwd || "", worktree: !!opts.worktree, place: opts.place || "tab",
  };
  const name = h("input", { class: "in", id: "na-name", placeholder: "e.g. discount codes" });
  const cwd = h("input", { class: "in mono", id: "na-cwd", value: st.cwd, placeholder: "Folder" });
  const custom = h("input", { class: "in mono", placeholder: "command to run", hidden: true, "aria-label": "Custom command" });
  const args = h("input", { class: "in mono", id: "na-args", placeholder: "extra arguments (optional)" });
  const prompt = h("textarea", { class: "in", id: "na-p", rows: "3", placeholder: "Sent once the agent is ready (optional)" });
  const gitNote = h("span", { class: "meta" });
  const wtBox = h("input", { type: "checkbox" });
  wtBox.checked = st.worktree;
  const machineSel = h("select", { class: "in", id: "na-m" }, h("option", { value: "" }, "This computer"),
    ...(store.raw.machines || []).filter((m) => m.status === "connected").map((m) => h("option", { value: m.alias }, m.alias)));
  machineSel.value = st.machine || "";
  const preview = h("span", { class: "mono meta grow trunc" });
  const chips = h("div", { class: "row", style: { flexWrap: "wrap", gap: "6px" } });

  const command = () => {
    const base = st.kind === "custom" ? custom.value.trim() : AGENTS.find((a) => a[0] === st.kind)[2];
    return [base, args.value.trim()].filter(Boolean).join(" ");
  };
  const refresh = () => {
    chips.replaceChildren(...AGENTS.map(([k, label]) => h("button", { type: "button", class: "chip" + (st.kind === k ? " on" : ""),
      onclick: () => { st.kind = k; custom.hidden = k !== "custom"; refresh(); } }, k !== "custom" ? kindIcon(k) : null, label)));
    preview.textContent = `hd run${st.machine ? " --on " + st.machine : ""}${wtBox.checked ? " --worktree <task>" : ""} -- ${command() || "(shell)"}`;
  };
  const checkGit = async () => {
    st.cwd = cwd.value.trim();
    gitNote.textContent = "";
    if (!st.cwd) return;
    try {
      const info = await conn.rpc("git.info", st.machine ? { path: st.cwd, machine: st.machine } : { path: st.cwd });
      gitNote.textContent = info.is_repo ? `✓ git repo · ${info.branch}${info.dirty ? ` · ${info.dirty} uncommitted` : ""}` : "not a git repo";
      wtBox.disabled = !info.is_repo;
      if (!info.is_repo) wtBox.checked = false;
    } catch (e) { gitNote.textContent = e.message; }
  };
  const recent = [...new Set(store.spaces.map((s) => s.cwd))].slice(0, 5);
  cwd.addEventListener("change", checkGit);
  machineSel.addEventListener("change", () => { st.machine = machineSel.value || null; cwd.value = ""; refresh(); checkGit(); });
  [custom, args].forEach((el) => el.addEventListener("input", refresh));
  wtBox.addEventListener("change", refresh);

  const start = async () => {
    const params = { command: command(), cwd: cwd.value.trim(), name: name.value.trim() };
    if (st.machine) params.machine = st.machine;
    if (wtBox.checked) params.worktree = { task: params.name || `${st.kind}-${Date.now() % 10000}` };
    const place = document.querySelector('input[name="na-place"]:checked')?.value || "tab";
    if (place === "split" && focused && (focused.machine || "local") === (st.machine || "local")) {
      params.tab_id = focused.tab_id; params.split_from = focused.id;
    }
    try {
      const pane = await conn.rpc("pane.create", params);
      closeModal();
      if (place !== "background") actions.focusPane(pane.id);
      const text = prompt.value.trim();
      if (text) {
        conn.rpc("pane.wait", { pane: pane.id, states: ["idle", "blocked"], timeout: 25 }).catch(() => {})
          .finally(() => conn.rpc("pane.send", { pane: pane.id, text }).catch(errorToast));
      }
    } catch (e) { errorToast(e); }
  };
  const radio = (value, label) => h("label", { class: "ck" },
    h("input", { type: "radio", name: "na-place", value, checked: st.place === value ? true : null }), label);

  openModal({
    size: "", label: "New agent",
    head: h("div", { class: "mhead" }, h("h2", {}, "New agent"), h("span", { class: "meta" }, space ? `in ${space.name}` : "")),
    body: h("div", { class: "mbody" },
      h("div", {}, h("span", { class: "lab" }, "Agent"), chips, custom),
      h("div", { class: "row", style: { gap: "10px", alignItems: "flex-start" } },
        h("div", { class: "grow" }, h("label", { class: "lab", for: "na-name" }, "Name"), name),
        h("div", { class: "grow" }, h("label", { class: "lab", for: "na-m" }, "Machine"), machineSel)),
      h("div", {}, h("label", { class: "lab", for: "na-cwd" }, "Folder"),
        h("div", { class: "row" }, cwd, h("button", { class: "btn", type: "button", onclick: async () => {
          const path = await chooseFolder(st.machine, cwd.value.trim());
          if (path) { cwd.value = path; checkGit(); }
        } }, icon("folder"), "Choose…")),
        h("div", { class: "row", style: { flexWrap: "wrap", marginTop: "6px" } },
          recent.length ? h("span", { class: "meta" }, "Recent") : null,
          ...recent.map((r) => h("button", { class: "chip sm", type: "button", title: r,
            onclick: () => { cwd.value = r; checkGit(); } }, r.split(/[\\/]/).pop())), gitNote)),
      h("div", { class: "box" }, h("label", { class: "ck" }, wtBox, "Work in a new git worktree (branch hd/<name>)")),
      h("div", { class: "row", style: { gap: "18px" } }, radio("tab", "New tab"), radio("split", "Split current pane"),
        radio("background", "Background")),
      h("div", {}, h("label", { class: "lab", for: "na-p" }, "First prompt"), prompt),
      h("div", {}, h("label", { class: "lab", for: "na-args" }, "Arguments"), args)),
    foot: [preview, h("button", { class: "btn", onclick: closeModal }, "Cancel"),
      h("button", { class: "btn pri", onclick: start }, "Start agent")],
  });
  refresh();
  checkGit();
  setTimeout(() => name.focus(), 0);
}
