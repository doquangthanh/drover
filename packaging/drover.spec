# PyInstaller spec. Windows: one file dist/drover.exe (window + CLI + daemon). Linux: folder dist/drover/ with the
# Python `dr` (CLI + TUI); CI adds the Rust window `drover` and daemon `drover-server` (hybrid bundle, no Qt).
# Build:  uv run pyinstaller packaging/drover.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Run first: npm --prefix frontend ci && npm --prefix frontend run build  (writes src/drover/web_dist/)
if not os.path.isfile(os.path.join(SPECPATH, "..", "src", "drover", "web_dist", "index.html")):
    raise SystemExit("web_dist missing: run `npm --prefix frontend ci && npm --prefix frontend run build` first")

datas = collect_data_files("drover", includes=["web/**/*", "web_dist/**/*", "status/rules/*.toml", "tui/*.tcss"])
hidden = collect_submodules("drover") + collect_submodules("desktop_notifier") + collect_submodules("claude_agent_sdk")
try:  # `dr tui` needs Textual (optional extra): bundle it only when the build environment has it
    import textual  # noqa: F401
    datas += collect_data_files("textual")
    hidden += collect_submodules("textual")
except ImportError:
    pass
if sys.platform == "win32":
    datas += collect_data_files("winpty", includes=["*.exe"])  # ConPTY helpers (OpenConsole.exe, winpty-agent.exe)
    hidden += ["winpty", "win32timezone"]  # win32timezone: imported lazily (pywin32), PyInstaller can't see it
# Linux: the window is the Rust `drover`, so no pywebview/Qt (the Python launcher then falls back to the browser).
LINUX_EXCLUDES = ["webview", "qtpy", "PyQt6"] if sys.platform == "linux" else []
ICON ={"icon": "drover.ico"} if sys.platform == "win32" else {}  # Linux executables take no icon


def analysis(script):
    # setuptools/pkg_resources: build-time only, but bundling them adds PyInstaller's pyi_rth_setuptools hook, which
    # imports setuptools (~0.5 s) on every start, i.e. on every `dr` call agents make.
    return Analysis([script], pathex=["../src"], datas=datas, hiddenimports=hidden,
                    excludes=["tkinter", "setuptools", "pkg_resources", "_distutils_hack", *LINUX_EXCLUDES])


if sys.platform == "win32":
    a_app = analysis("drover_entry.py")
    pyz_app = PYZ(a_app.pure)
    # Single file dist/drover.exe: window with no args, `drover <cmd>` is the CLI, `drover server run` the daemon.
    EXE(pyz_app, a_app.scripts, a_app.binaries, a_app.datas, [], name="drover", console=False, **ICON)
    # Plus folder dist/drover-cli/ (no onefile unpacking per call): zipped as drover-cli-windows-x64.zip, installed
    # by the daemon into <state>/runtime/<version>/ (windows_cli_runtime_installer). The Python CLI is dr-py.exe;
    # CI adds the Rust dr.exe next to it, which answers agent commands itself and runs dr-py.exe for the rest.
    a_cli = analysis("dr_entry.py")
    exe_cli = EXE(PYZ(a_cli.pure), a_cli.scripts, [], exclude_binaries=True, name="dr-py", console=True, **ICON)
    COLLECT(exe_cli, a_cli.binaries, a_cli.datas, name="drover-cli")
else:
    a_dr = analysis("dr_entry.py")
    exe_dr = EXE(PYZ(a_dr.pure), a_dr.scripts, [], exclude_binaries=True, name="dr", console=True, **ICON)
    COLLECT(exe_dr, a_dr.binaries, a_dr.datas, name="drover")
