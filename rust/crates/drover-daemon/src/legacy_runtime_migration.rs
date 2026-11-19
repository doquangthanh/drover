//! Windows installs up to 0.1.43 ran the daemon from `<state>/runtime/<version>/`, owned by a one-file Python
//! `drover.exe`. A 0.1.43 daemon updates that runtime folder in place (it looks like a release bundle), so a newer
//! daemon can find itself there. It then moves the install to the shared layout, once:
//! 1. copy its folder to the app folder (`<state>/app`),
//! 2. replace the old `drover.exe` with the Tauri one (autostart and `dr.cmd` shims call that path; the Tauri
//!    `drover.exe` forwards their `server run` / CLI arguments to `dr`),
//! 3. start the daemon from the app folder; this process exits without serving.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use crate::self_update::{VERSION, version_tuple};
use crate::self_update_apply::{VERSION_FILE, bundle_dir, default_app_dir, is_bundle, swap};

/// Called by `serve` before anything starts. True: the daemon now starts from the app folder; don't serve here.
pub fn hand_over(host: &str, foreground: bool, keep: &(String, u16)) -> bool {
    let Some(here) = bundle_dir() else { return false };
    let runtime = crate::paths::state_dir().join("runtime");
    if !same_path(here.parent(), &runtime) {
        return false;
    }
    let app = default_app_dir();
    if let Err(e) = copy_into_app(&here, &app) {
        crate::log::warn(&format!("could not move to {}: {e}; staying in the runtime folder", app.display()));
        return false;
    }
    let owner = owner_exe(&here, &runtime);
    if let Some(owner) = &owner {
        replace_owner(owner, &app.join("drover.exe"));
    }
    // The in-place update lost the runtime's `.complete`. Put it back: without it an old drover.exe that still runs
    // (owner not found) wipes this folder and reinstalls its own version; with it, it starts this dr.exe, which
    // comes back here and hands over to the app folder again.
    let _ = std::fs::write(here.join(".complete"), owner.map(|o| o.to_string_lossy().into_owned()).unwrap_or_default());
    let mut cmd = Command::new(app.join("dr.exe"));
    cmd.args(["server", "run"]);
    if !foreground {
        cmd.arg("--background");
    }
    if host != "127.0.0.1" {
        cmd.args(["--listen", host]);
    }
    if !keep.0.is_empty() {
        cmd.env("DROVER_KEEP_TOKEN", &keep.0).env("DROVER_KEEP_PORT", keep.1.to_string());
    }
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)]
    std::os::windows::process::CommandExt::creation_flags(&mut cmd, 0x0800_0000 | 0x0000_0200); // no console, new group
    match cmd.spawn() {
        Ok(_) => {
            crate::log::info(&format!("moved to {}; the daemon starts from there", app.display()));
            true
        }
        Err(e) => {
            crate::log::warn(&format!("could not start {}: {e}", app.join("dr.exe").display()));
            false
        }
    }
}

fn same_path(a: Option<&Path>, b: &Path) -> bool {
    a.is_some_and(|a| norm(a) == norm(b))
}

/// Copy the bundle into `app` unless it already holds this version or newer (atomic swap, like an update).
fn copy_into_app(here: &Path, app: &Path) -> Result<(), String> {
    let have = std::fs::read_to_string(app.join(VERSION_FILE)).unwrap_or_default();
    if is_bundle(app) && version_tuple(&have) >= version_tuple(VERSION) {
        return Ok(());
    }
    let parent = app.parent().ok_or("app folder has no parent")?;
    let tmp = parent.join(format!(".drover-update-{}", crate::chat::new_id()));
    let result = (|| {
        copy_dir(here, &tmp.join("new")).map_err(|e| format!("copy failed: {e}"))?;
        std::fs::create_dir_all(app).map_err(|e| e.to_string())?;
        swap(app, &tmp.join("new"), &tmp.join("old"))
    })();
    let _ = std::fs::remove_dir_all(&tmp);
    result?;
    let _ = std::fs::write(app.join(VERSION_FILE), VERSION);
    Ok(())
}

fn copy_dir(from: &Path, to: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(to)?;
    for entry in std::fs::read_dir(from)? {
        let entry = entry?;
        let target = to.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_dir(&entry.path(), &target)?;
        } else {
            std::fs::copy(entry.path(), target)?;
        }
    }
    Ok(())
}

/// The one-file drover.exe that installed the runtime. Its path is in the runtime's `.complete` marker (usually
/// deleted by the in-place update), else in the files it wrote: the `dr.cmd` / `hd.cmd` shims and the autostart
/// script. Paths inside the state folder (runtime, app) are not it.
fn owner_exe(here: &Path, runtime: &Path) -> Option<PathBuf> {
    let state = crate::paths::state_dir();
    let leftovers = std::fs::read_dir(runtime).into_iter().flatten().flatten()
        .filter(|e| e.file_name().to_string_lossy().starts_with(".drover-update-"))
        .map(|e| e.path().join("old").join(".complete"));
    let markers = std::iter::once(here.join(".complete")).chain(leftovers)
        .filter_map(|marker| std::fs::read_to_string(marker).ok())
        .map(|text| PathBuf::from(text.trim()));
    let startup = std::env::var_os("APPDATA")
        .map(|a| Path::new(&a).join(r"Microsoft\Windows\Start Menu\Programs\Startup\drover-daemon.cmd"));
    let scripts = [Some(state.join("shims").join("dr.cmd")), Some(state.join("shims").join("hd.cmd")), startup]
        .into_iter().flatten()
        .filter_map(|f| std::fs::read_to_string(f).ok())
        .flat_map(|text| quoted_exes(&text));
    markers.chain(scripts).find(|p| p.is_file() && !inside(p, &state))
}

fn norm(p: &Path) -> String {
    p.to_string_lossy().trim_start_matches(r"\\?\").trim_end_matches('\\').replace('/', "\\").to_lowercase()
}

fn inside(p: &Path, dir: &Path) -> bool {
    norm(p).starts_with(&format!("{}\\", norm(dir)))
}

/// `"C:\x\drover.exe"` paths in a batch file.
fn quoted_exes(text: &str) -> Vec<PathBuf> {
    text.split('"').skip(1).step_by(2).filter(|s| s.to_lowercase().ends_with(".exe")).map(PathBuf::from).collect()
}

/// Put the Tauri `drover.exe` where the old one is. The running old copy is renamed aside (`.old`, `.old2`...),
/// which Windows allows; the Tauri launcher deletes those on its next start.
fn replace_owner(owner: &Path, tauri: &Path) {
    if std::fs::read(owner).ok() == std::fs::read(tauri).ok() {
        return;
    }
    let Some(aside) = (1..50).map(|n| {
        let suffix = if n == 1 { ".old".to_string() } else { format!(".old{n}") };
        PathBuf::from(format!("{}{suffix}", owner.display()))
    }).find(|p| !p.exists() || std::fs::remove_file(p).is_ok()) else { return };
    if let Err(e) = std::fs::rename(owner, &aside) {
        crate::log::warn(&format!("could not move {} aside: {e}", owner.display()));
        return;
    }
    if let Err(e) = std::fs::copy(tauri, owner) {
        crate::log::warn(&format!("could not install the new drover.exe: {e}"));
        let _ = std::fs::rename(&aside, owner);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_the_owner_in_shim_text_and_compares_paths_loosely() {
        let shim = "@if not exist \"C:\\s\\runtime\\0.1.43\\.complete\" goto drover\r\n@\"C:\\s\\runtime\\0.1.43\\dr.exe\" %*\r\n\
                    @exit /b %errorlevel%\r\n:drover\r\n@\"C:\\Users\\me\\Desktop\\drover.exe\" %*\r\n";
        let found = quoted_exes(shim);
        assert_eq!(found, [PathBuf::from(r"C:\s\runtime\0.1.43\dr.exe"), PathBuf::from(r"C:\Users\me\Desktop\drover.exe")]);
        assert!(inside(&found[0], Path::new(r"c:\S")) && !inside(&found[1], Path::new(r"C:\s")));
        assert!(same_path(Some(Path::new(r"\\?\C:\S\Runtime\")), Path::new(r"c:\s\runtime")));
    }
}
