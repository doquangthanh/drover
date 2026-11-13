// Settings > Appearance: theme cards and file-icon sets, each a small live preview (choice is kept per device).
import { h } from "../dom.js";
import { THEMES, chosenTheme, setTheme } from "../theme.js";
import { ICON_SETS, chosenIconSet, setIconSet, fileIcon } from "../file-icons.js";

const PREVIEW = {
  dark: { cv: "#131518", ch: "#101114", cp: "#17191d", fg: "#eeeeef", mu: "#98999b", ac: "#96b2d7", bd: "rgba(255,255,255,.1)", ok: "#a6bd91", note: "default" },
  light: { cv: "#eef0f3", ch: "#e4e7eb", cp: "#ffffff", fg: "#1a1c20", mu: "#5b6270", ac: "#2f6bb3", bd: "rgba(0,0,0,.1)", ok: "#1a7f4b", note: "" },
  midnight: { cv: "#0b0e17", ch: "#080a12", cp: "#0f1320", fg: "#e6e9f5", mu: "#8e97b5", ac: "#7c9cff", bd: "rgba(255,255,255,.1)", ok: "#8fd3a8", note: "" },
};

function themeCard(id, label, on) {
  const p = PREVIEW[id];
  const av = (c) => h("span", { class: "pav", style: { background: c } });
  const row = (c, t) => h("div", { class: "prow" }, av(c), t);
  const vars = `--cv:${p.cv};--ch:${p.ch};--cp:${p.cp};--fg:${p.fg};--mu:${p.mu};--ac:${p.ac};--bd:${p.bd}`;
  return h("button", { class: "tcard" + (on ? " on" : ""), onclick: () => setTheme(id), "aria-pressed": on ? "true" : "false" },
    h("div", { class: "tprev", style: vars },
      h("div", { class: "ptb" }, av(p.ac), "herd", h("span", { class: "grow" }), "shop-api"),
      h("div", { class: "pbody" },
        h("div", { class: "psb" }, row("#24877b", "shop-api"), row("#b9602f", "blog"), row("#4e7fe0", "docs")),
        h("div", { class: "ptm" }, h("div", {}, h("span", { style: { color: p.ok } }, "●"), " Update(src/auth/jwt.py)"),
          h("div", {}, "  ⎿ 3 additions, 1 removal"), h("div", { style: { color: p.ac } }, "❯ 1. Yes")))),
    h("div", { class: "tname" }, label, p.note ? h("span", { class: "dim" }, ` · ${p.note}`) : null));
}

const SAMPLE = [["docs", true, true, 0], ["README.md", false, false, 1], ["src", true, true, 0], ["app.py", false, false, 1],
  ["App.tsx", false, false, 1], ["package.json", false, false, 0], ["Dockerfile", false, false, 0]];

function iconCard([id, label, tip], on) {
  const rows = SAMPLE.map(([name, dir, open, depth]) => h("div", { class: "irow", style: { paddingLeft: depth ? "17px" : "0" } },
    h("span", { class: "icr" }, dir ? (open ? "▾" : "▸") : ""), fileIcon(name, dir, open, id), name));
  return h("button", { class: "icard" + (on ? " on" : ""), onclick: () => setIconSet(id), "aria-pressed": on ? "true" : "false", title: tip },
    h("div", { class: "ilist" + (id === "line" ? " line" : "") }, ...rows),
    h("div", { class: "tname" }, label, h("span", { class: "dim" }, ` · ${tip.split(" (")[0].toLowerCase()}`)));
}

export function appearancePanel(repaint) {
  const theme = chosenTheme();
  return h("div", { class: "appearance" },
    h("div", { class: "alab" }, "THEME"),
    h("div", { class: "agrid" }, ...["dark", "light", "midnight"].map((id) => themeCard(id, THEMES.find((t) => t[0] === id)[1], theme === id))),
    h("label", { class: "ck", style: { margin: "10px 0 0" } }, h("input", { type: "checkbox", checked: theme === "auto" ? true : null,
      onchange: (e) => { setTheme(e.target.checked ? "auto" : "dark"); repaint(); } }), "Auto: follow the system (light or dark)"),
    h("div", { class: "alab", style: { marginTop: "22px" } }, "FILE ICONS"),
    h("div", { class: "agrid" }, ...ICON_SETS.map((s) => iconCard(s, chosenIconSet() === s[0]))),
    h("p", { class: "meta", style: { lineHeight: "1.6", marginTop: "18px" } }, "In ", h("span", { class: "mono" }, "settings.toml"), ": ",
      h("span", { class: "mono" }, 'theme = "light"'), " and ", h("span", { class: "mono" }, 'file_icons = "badge"'),
      ". A choice made in the app is kept per device (phone and desktop can differ) and wins over the file."));
}
