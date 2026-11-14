# PyInstaller spec: one folder (dist/herd/) holding herd.exe (window) + hd.exe (CLI/daemon).
# Build:  uv run pyinstaller packaging/herd.spec --noconfirm
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Run first: npm --prefix frontend ci && npm --prefix frontend run build  (writes src/herd/web_dist/)
if not os.path.isfile(os.path.join(SPECPATH, "..", "src", "herd", "web_dist", "index.html")):
    raise SystemExit("web_dist missing: run `npm --prefix frontend ci && npm --prefix frontend run build` first")

datas = collect_data_files("herd", includes=["web/**/*", "web_dist/**/*", "status/rules/*.toml"])
datas += collect_data_files("winpty", includes=["*.exe"])  # ConPTY helpers (OpenConsole.exe, winpty-agent.exe)
hidden = collect_submodules("herd") + collect_submodules("desktop_notifier") + ["winpty"]


def analysis(script):
    return Analysis([script], pathex=["../src"], datas=datas, hiddenimports=hidden, excludes=["tkinter"])


a_hd = analysis("hd_entry.py")
a_app = analysis("herd_entry.py")
pyz_hd = PYZ(a_hd.pure)
pyz_app = PYZ(a_app.pure)

exe_hd = EXE(pyz_hd, a_hd.scripts, [], exclude_binaries=True, name="hd", console=True, icon="herd.ico")
exe_app = EXE(pyz_app, a_app.scripts, [], exclude_binaries=True, name="herd", console=False, icon="herd.ico")

coll = COLLECT(
    exe_hd, exe_app,
    a_hd.binaries, a_hd.datas, a_app.binaries, a_app.datas,
    name="herd",
)

