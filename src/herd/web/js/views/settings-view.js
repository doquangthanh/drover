// Settings: every config file editable in place (validated on save), appearance, detection rules + tester.
import { conn } from "../connection.js";
import { h, kindIcon, errorToast, toast, setTopExtra } from "../dom.js";
import { ruleTester } from "./rule-tester.js";
import { appearancePanel } from "./appearance-panel.js";

// [id, label, file, section marker to scroll to]
const SECTIONS = [
  ["general", "General", "settings.toml"], ["appearance", "Appearance"], ["notifications", "Notifications", "settings.toml", "[notify]"],
  ["keyboard", "Keyboard", "keys.toml"], ["agents", "Agents & detection"], ["machines", "Machines", "machines.toml"],
  ["policy", "Agent policy", "settings.toml", "[orchestration]"], ["docs", "Notes for agents", "AGENTS.md"],
];
const st = { section: "general", rule: null };

const STARTER_RULE = `id = "myagent"
aliases = []
resume = ""

[[rules]]
id = "needs_answer"
state = "blocked"
priority = 900
region = "bottom(15)"
regex = ['Do you want to proceed']
`;

function filePanel(file, data, root, marker, withTest) {
  const editor = h("textarea", { class: "in code", spellcheck: "false", "aria-label": file.name }, file.text);
  const save = async () => {
    try { await conn.rpc("settings.write", { name: file.name, text: editor.value }); toast(`Saved ${file.name}`, "herd reloads it within 2 seconds."); renderSettings(root); }
    catch (e) { errorToast(e); }
  };
  editor.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); } });
  if (marker) setTimeout(() => { const i = file.text.indexOf(marker); if (i > 0) editor.scrollTop = file.text.slice(0, i).split("\n").length * 19 - 40; }, 0);
  return h("div", { class: "panel" }, h("div", { class: "ph s32" }, h("span", { class: "mono grow trunc" }, file.name),
    h("span", { class: "meta" }, file.exists ? "" : "new file"),
    withTest ? h("button", { class: "btn sm", onclick: () => conn.rpc("notify.test").catch(errorToast) }, "Test notification") : null,
    window.pywebview?.api?.open_path ? h("button", { class: "btn sm", onclick: () => window.pywebview.api.open_path(file.path) }, "Open in editor") : null,
    h("button", { class: "btn sm pri", onclick: save }, "Save")),
  ...data.errors.filter((e) => e.startsWith(file.name)).map((e) => h("div", { class: "errtext", style: { padding: "6px 12px" } }, e)), editor);
}

function rulesColumn(rules, data, root) {
  const files = new Set(data.files.map((f) => f.name));
  const add = async () => {
    const id = window.prompt("Agent id for the new rule file (e.g. aider)");
    if (!id || !/^[a-z0-9_-]+$/.test(id)) return;
    try { await conn.rpc("settings.write", { name: `rules/${id}.toml`, text: STARTER_RULE.replace("myagent", id) }); st.rule = id; renderSettings(root); }
    catch (e) { errorToast(e); }
  };
  return h("div", { class: "scol" }, h("div", { class: "meta", style: { padding: "4px 10px 8px" } }, "Detection rules"),
    ...rules.map((r) => h("button", { class: "ag" + (st.rule === r.id ? " on" : ""), onclick: () => { st.rule = r.id; renderSettings(root); } },
      kindIcon(r.id), h("span", { class: "grow" }, r.id), h("span", { class: "meta" }, files.has(`rules/${r.id}.toml`) ? "yours" : r.source))),
    h("button", { class: "ag", style: { color: "var(--accent)" }, onclick: add }, "+ Add agent rules"));
}

export async function renderSettings(root) {
  let data;
  try { data = await conn.rpc("settings.files"); } catch (e) { root.replaceChildren(h("div", { class: "view errtext" }, e.message)); return; }
  let rules = [];
  try { rules = await conn.rpc("rules.list"); } catch { /* optional */ }
  const sec = SECTIONS.find((s) => s[0] === st.section) || SECTIONS[0];
  const byName = (n) => data.files.find((f) => f.name === n) || { name: n, path: `${data.dir}/${n}`, exists: false, text: "" };
  setTopExtra("settings", {
    meta: h("span", { class: "meta mono" }, `${data.dir} · plain files, reloads on save`),
    right: [h("span", { style: { fontSize: "12px", color: data.errors.length ? "var(--error)" : "var(--done)" } }, data.errors.length ? `${data.errors.length} problem${data.errors.length > 1 ? "s" : ""}` : "✓ All files valid"),
      window.pywebview?.api?.open_path ? h("button", { class: "btn", onclick: () => window.pywebview.api.open_path(data.dir) }, "Open folder") : null] });

  const nav = h("div", { class: "snav" },
    ...SECTIONS.map(([id, label]) => h("button", { class: "nav" + (id === sec[0] ? " on" : ""), onclick: () => { st.section = id; renderSettings(root); } }, label)),
    h("span", { class: "grow" }),
    h("div", { class: "snote" }, "Every setting is a file. ", h("span", { class: "mono" }, "AGENTS.md"), " in the folder explains them, so an agent can change herd for you."));

  const testBox = h("div", { class: "row rtest" });
  let main;
  if (sec[0] === "appearance") main = h("div", { class: "smain" }, h("div", { class: "panel" }, appearancePanel(() => renderSettings(root))));
  else if (sec[0] === "agents") {
    if (!st.rule || !rules.some((r) => r.id === st.rule)) st.rule = rules[0]?.id || null;
    const own = st.rule && data.files.find((f) => f.name === `rules/${st.rule}.toml`);
    main = h("div", { class: "smain" },
      own ? filePanel(own, data, root, null, false) : h("div", { class: "panel", style: { padding: "12px", gap: "8px" } },
        h("div", { class: "meta" }, st.rule ? `${st.rule} uses herd's built-in rules.` : "No agents yet."),
        st.rule ? h("button", { class: "btn", style: { alignSelf: "flex-start" }, onclick: async () => {
          try { await conn.rpc("settings.write", { name: `rules/${st.rule}.toml`, text: STARTER_RULE.replace("myagent", st.rule) }); renderSettings(root); } catch (e) { errorToast(e); }
        } }, `Create rules/${st.rule}.toml to override them`) : null),
      testBox);
    ruleTester(testBox);
  } else main = h("div", { class: "smain" }, filePanel(byName(sec[2]), data, root, sec[3], sec[0] === "notifications"));
  root.replaceChildren(h("div", { class: "vsplit settings-split ssplit" }, nav, sec[0] === "agents" ? rulesColumn(rules, data, root) : null, main));
}
