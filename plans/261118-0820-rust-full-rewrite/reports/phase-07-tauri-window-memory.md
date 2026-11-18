# Phase 07: Tauri window memory (2026-11-18)

Release `drover` (Tauri 2.12, WebKitGTK 2.50.4) vs the PyQt/QtWebEngine window, same page, same Rust daemon.
PSS of the window process tree; ±15 MB run to run.

| Case | Window total | Web process |
|---|---|---|
| Tauri, blank page | 179 MB | 93 MB |
| Tauri, UI, 0 panes | 253 MB | 167 MB |
| Tauri, UI, 1 pane | 242 MB | 156 MB |
| Tauri, UI, 4 panes | 253 MB | 167 MB |
| PyQt window, UI (RSS 396 MB; shares Qt libs with other open windows) | 160 MB | - |

Tried, no real gain (all within noise): WEBKIT_DISABLE_COMPOSITING_MODE, WEBKIT_DISABLE_DMABUF_RENDERER, both,
cache model DocumentViewer (code, reverted). JSC_useJIT=false saved ~20 MB but slows the UI: not taken.

Findings
- ~180 MB is WebKitGTK's fixed cost; the React UI adds ~75 MB of runtime memory (bundle is only ~1 MB);
  terminals add almost nothing per pane.
- On Linux a Tauri window is not lighter than the Qt one. The real saving is single instance (verified: a second
  `drover` exits in 0.09 s and focuses the first; the machine had ~6 drover window processes at once) and shipping
  a 5.5 MB binary without Python/Qt.
- Found while testing: a daemon started from inside a Claude Code session passed CLAUDECODE / CLAUDE_CODE_* to every
  pane (claude there turned transcripts off, hooks hit the other session's socket). `launch::pane_env` now drops them.

## IME check (2026-11-18): blocker
Same synthetic typing (`xdotool type`, ibus Telex active) into the same shell pane:
- PyQt window: `echo ácii-ok-123` (clean; Telex turning "as" into "á" is expected).
- Tauri window: `echo echo ácii-ok-o ác ii-ok-` (input duplicated and scrambled). Same with GTK_IM_MODULE=xim.
The frontend only uses xterm.js 5.5.0 `term.onData`, so the duplication comes from xterm.js composition handling
under WebKitGTK. Blocks daily use for Vietnamese input until fixed (check newer xterm.js, or a composition-aware
input path in `frontend/src/terminals/terminal-registry.ts`). Tauri renders powerline glyphs that the Qt window shows
as boxes.

## Hands-on check of the Tauri window (2026-11-18, xdotool + screenshots)
| Item | Result |
|---|---|
| ibus (Telex) typing | **broken**: first word duplicated, text scrambled, even plain ASCII (`echo echo COPYME12345`); prefix keys (Ctrl+A then a letter) never arrive. Qt window: clean. |
| Copy / paste | works (drag-select copies, Ctrl+Shift+V pastes). Double-click select via xdotool did not select (not checked by hand). |
| Desktop bridge (`window.pywebview.api`) | was **broken**: Tauri 2 refuses app commands from the remote daemon origin ("not allowed by ACL"). Fixed: build.rs AppManifest + capability grants the 4 commands. |
| Title bar follows theme | was broken (GTK variant never set); fixed via GTK prefer-dark; verified dark frame. Light not checked. |
| Native folder picker | not reached: its entry needs Ctrl+A S, blocked by the ibus bug. Bridge now works, dialog itself unverified. |
| Burst output (seq 1..300000) | renders to the end; settles in 2.6-2.7 s (Qt 3.0 s); first run 5.7 s (cold). |

## IME fix (2026-11-18)
WebKitGTK + ibus no-preedit: letters arrive as keyup only; a word commits as keydown(229) + input(insertFromComposition)
+ compositionend with no compositionstart. Punctuation (`?`) commits at once, *before* its keyup; letters are held.
`webkit-ime-guard.ts` sends commits itself and takes the key after the prefix from the commit (first char) or, if held,
from the keyup (IME reset by blur+focus before the action, held letter dropped from the next commit).
Checked: `echo tiếng việt` clean, Ctrl+A ? opens help and Escape closes it. Not run: Ctrl+A + held letter.
Note: very fast synthetic chords (`xdotool key ctrl+a`) were sometimes lost; explicit keydown/keyup with delays work.
