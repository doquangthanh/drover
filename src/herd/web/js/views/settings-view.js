// Settings: every config file editable in place (validated on save) + detection rule tester.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h, kindIcon, errorToast, toast } from "../dom.js";

const st = { file: "settings.toml", testPane: null };

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

async function ruleTester(box) {
  const panes = store.panes.filter((p) => !p.machine || p.machine === "local");
  if (!st.testPane || !panes.some((p) => p.id === st.testPane)) st.testPane = panes[0]?.id || null;
  if (!st.testPane) { box.replaceChildren(h("div", { class: "meta" }, "Start an agent to test rules against its screen.")); return; }
  const sel = h("select", { class: "in", style: { width: "220px", height: "28px" }, "aria-label": "Pane to test",
    onchange: () => { st.testPane = sel.value; ruleTester(box); } }, ...panes.map((p) => h("option", { value: p.id }, `${p.name} (${p.kind})`)));
  sel.value = st.testPane;
  let r;
  try { r = await conn.rpc("rules.test", { pane: st.testPane }); } catch (e) { box.replaceChildren(h("div", { class: "errtext" }, e.message)); return; }
  box.replaceChildren(
    h("div", { class: "row" }, h("b", { class: "grow" }, "Rule tester"), sel,
      h("button", { class: "btn", onclick: () => ruleTester(box) }, "Run again")),
    h("div", { class: "meta" }, `kind ${r.kind} · title “${r.title}”${r.osc7501 ? " · OSC 7501 says " + r.osc7501 : ""}`),
    h("div", { class: "codebox", style: { maxHeight: "200px" } }, r.screen.join("\n")),
    h("div", {}, h("div", { class: "rt meta" }, h("span", {}, "Rule"), h("span", {}, "Prio"), h("span", {}, "Region"), h("span", {}, "Result")),
      ...r.results.map((x) => h("div", { class: "rt" }, h("span", { style: { color: x.matched ? "var(--blocked)" : "" } }, `${x.rule_id} → ${x.state}`),
        h("span", {}, x.priority), h("span", { class: "mono" }, x.region), h("span", { class: x.matched ? "" : "meta" }, x.matched ? "match" : "no match")))),
    h("div", { class: "row" }, h("span", {}, "Detected:"), h("b", {}, r.detected || "nothing (activity fallback)"),
      h("span", { class: "meta" }, `· current state ${r.state}`)));
}

export async function renderSettings(root) {
  let data;
  try { data = await conn.rpc("settings.files"); } catch (e) { root.replaceChildren(h("div", { class: "view errtext" }, e.message)); return; }
  let rules = [];
  try { rules = await conn.rpc("rules.list"); } catch { /* optional */ }
  const file = data.files.find((f) => f.name === st.file) || data.files[0];
  const editor = h("textarea", { class: "in code", spellcheck: "false", "aria-label": file.name }, file.text);
  const status = h("span", { class: "meta" }, data.errors.length ? "" : "✓ All files valid");
  const save = async () => {
    try { await conn.rpc("settings.write", { name: file.name, text: editor.value }); toast(`Saved ${file.name}`, "herd reloads it within 2 seconds."); renderSettings(root); }
    catch (e) { errorToast(e); }
  };
  const nav = h("div", { style: { width: "220px", flex: "none", padding: "10px 8px", borderRight: "1px solid var(--border)", overflow: "auto" } },
    h("div", { class: "sec" }, "Files"),
    ...data.files.map((f) => h("button", { class: "nav" + (f.name === file.name ? " on" : ""), onclick: () => { st.file = f.name; renderSettings(root); } },
      f.name, f.exists ? "" : h("span", { class: "meta" }, " · new"))),
    h("button", { class: "nav", style: { color: "var(--accent)" }, onclick: async () => {
      const id = window.prompt("Agent id for the new rule file (e.g. aider)");
      if (!id || !/^[a-z0-9_-]+$/.test(id)) return;
      try { await conn.rpc("settings.write", { name: `rules/${id}.toml`, text: STARTER_RULE.replace("myagent", id) }); st.file = `rules/${id}.toml`; renderSettings(root); }
      catch (e) { errorToast(e); }
    } }, "+ Add agent rules"),
    h("div", { class: "sec" }, "Loaded rules"),
    ...rules.map((r) => h("div", { class: "lrow", style: { padding: "0 10px", minHeight: "28px" } }, kindIcon(r.id), h("span", { class: "grow" }, r.id),
      h("span", { class: "meta" }, r.source))),
    h("div", { class: "box", style: { marginTop: "12px", fontSize: "12px", color: "var(--muted)", lineHeight: "1.5" } },
      "Every setting is a file in ", h("span", { class: "mono", style: { wordBreak: "break-all" } }, data.dir), ". AGENTS.md there explains them so an agent can change herd for you."));
  const testBox = h("div", { class: "panel", style: { padding: "12px", gap: "10px" } });
  root.replaceChildren(h("div", { class: "vsplit" }, nav,
    h("div", { class: "grow", style: { display: "flex", flexDirection: "column", gap: "8px", minWidth: "0", overflow: "auto" } },
      h("div", { class: "panel" }, h("div", { class: "ph" }, h("span", { class: "mono grow" }, file.path), status,
        window.pywebview?.api?.open_path ? h("button", { class: "btn", onclick: () => window.pywebview.api.open_path(file.path) }, "Open in editor") : null,
        h("button", { class: "btn", onclick: () => conn.rpc("notify.test").catch(errorToast) }, "Test notification"),
        h("button", { class: "btn pri", onclick: save }, "Save")),
      ...data.errors.map((e) => h("div", { class: "errtext", style: { padding: "6px 12px" } }, e)), editor),
      testBox)));
  editor.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(); } });
  ruleTester(testBox);
}
