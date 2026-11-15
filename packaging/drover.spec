# PyInstaller spec. Windows: one file dist/drover.exe (window + CLI + daemon). Linux: folder dist/drover/ with drover + dr.
# Build:  uv run pyinstaller packaging/drover.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Run first: npm --prefix frontend ci && npm --prefix frontend run build  (writes src/drover/web_dist/)
if not os.path.isfile(os.path.join(SPECPATH, "..", "src", "drover", "web_dist", "index.html")):
    raise SystemExit("web_dist missing: run `npm --prefix frontend ci && npm --prefix frontend run build` first")

datas = collect_data_files("drover", includes=["web/**/*", "web_dist/**/*", "status/rules/*.toml"])
hidden = collect_submodules("drover") + collect_submodules("desktop_notifier") + collect_submodules("claude_agent_sdk")
if sys.platform == "win32":
    datas += collect_data_files("winpty", includes=["*.exe"])  # ConPTY helpers (OpenConsole.exe, winpty-agent.exe)
    hidden += ["winpty", "win32timezone"]  # win32timezone: imported lazily (pywin32), PyInstaller can't see it
if sys.platform == "linux":
    hidden += ["webview.platforms.qt", "qtpy", "PyQt6.QtWebEngineCore", "PyQt6.QtWebChannel"]  # pywebview picks its backend dynamically
ICON ={"icon": "drover.ico"} if sys.platform == "win32" else {}  # Linux executables take no icon


def analysis(script):
    return Analysis([script], pathex=["../src"], datas=datas, hiddenimports=hidden, excludes=["tkinter"])


a_app = analysis("drover_entry.py")
pyz_app = PYZ(a_app.pure)

if sys.platform == "win32":
    # Single file dist/drover.exe: window with no args, `drover <cmd>` is the CLI, `drover server run` the daemon.
    EXE(pyz_app, a_app.scripts, a_app.binaries, a_app.datas, [], name="drover", console=False, **ICON)
else:
    a_dr = analysis("dr_entry.py")
    pyz_dr = PYZ(a_dr.pure)
    exe_dr = EXE(pyz_dr, a_dr.scripts, [], exclude_binaries=True, name="dr", console=True, **ICON)
    exe_app = EXE(pyz_app, a_app.scripts, [], exclude_binaries=True, name="drover", console=False, **ICON)
    COLLECT(exe_dr, exe_app, a_dr.binaries, a_dr.datas, a_app.binaries, a_app.datas, name="drover")
