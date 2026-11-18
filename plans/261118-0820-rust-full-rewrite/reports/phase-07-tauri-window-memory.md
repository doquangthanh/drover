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
