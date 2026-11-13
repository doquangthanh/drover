// Detection rule tester: runs the rules against a live pane screen and shows which rule matched.
import { conn } from "../connection.js";
import { store } from "../store.js";
import { h } from "../dom.js";

const st = { pane: null };
const PILL = { blocked: ["blocked", "Needs you"], working: ["info", "Working"], done: ["ok", "Done"], idle: ["", "Idle"] };

export async function ruleTester(box) {
  const panes = store.panes.filter((p) => !p.machine || p.machine === "local");
  if (!st.pane || !panes.some((p) => p.id === st.pane)) st.pane = panes[0]?.id || null;
  if (!st.pane) { box.replaceChildren(h("div", { class: "panel", style: { flex: "1", padding: "12px" } }, h("div", { class: "meta" }, "Start an agent to test rules against its screen."))); return; }
  const sel = h("select", { class: "seg", "aria-label": "Pane to test", onchange: () => { st.pane = sel.value; ruleTester(box); } },
    ...panes.map((p) => h("option", { value: p.id }, `${p.name} · live screen`)));
  sel.value = st.pane;
  let r;
  try { r = await conn.rpc("rules.test", { pane: st.pane }); }
  catch (e) { box.replaceChildren(h("div", { class: "errtext" }, e.message)); return; }
  const [cls, text] = PILL[r.detected] || ["", r.detected || "no rule matched"];
  box.replaceChildren(
    h("div", { class: "panel", style: { flex: "1", minWidth: "0" } },
      h("div", { class: "ph s32" }, h("span", { class: "grow" }, "Test against"), sel, h("button", { class: "seg", onclick: () => ruleTester(box) }, "Run again")),
      h("div", { class: "codebox bare" }, `title: ${r.title || ""}\n${r.screen.join("\n")}`)),
    h("div", { class: "panel rtres" },
      h("div", { class: "rt meta" }, h("span", {}, "Rule"), h("span", {}, "Prio"), h("span", {}, "Region"), h("span", {}, "Result")),
      ...r.results.map((x) => h("div", { class: "rt" }, h("span", { style: { color: x.matched ? "var(--blocked)" : "" } }, `${x.rule_id} → ${x.state}`),
        h("span", {}, x.priority), h("span", { class: "mono" }, x.region), h("span", { class: x.matched ? "" : "meta", style: { color: x.matched ? "var(--blocked)" : "" } }, x.matched ? "match" : "no match"))),
      h("div", { class: "row", style: { marginTop: "12px" } }, h("span", {}, "Result"), h("span", { class: `pill ${cls}` }, text),
        h("span", { class: "meta" }, `current state ${r.state}${r.osc7501 ? " · OSC 7501 says " + r.osc7501 : ""}`))));
}
