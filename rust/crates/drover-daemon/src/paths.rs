//! Filesystem locations for config, state and logs. Same folders as the Python daemon (`app_paths.py`), so either
//! daemon can take over the other's session: Linux `~/.config/drover` + `~/.local/state/drover`, Windows
//! `%LOCALAPPDATA%/drover` for both. `DROVER_CONFIG_DIR` / `DROVER_STATE_DIR` override.

use std::path::{Path, PathBuf};

const APP: &str = "drover";

fn default_dir(config: bool) -> PathBuf {
    if cfg!(windows)
        && let Some(local) = std::env::var_os("LOCALAPPDATA")
    {
        return PathBuf::from(local).join(APP);
    }
    let base = if config { dirs::config_dir() } else { dirs::state_dir().or_else(dirs::data_local_dir) };
    base.unwrap_or_else(|| PathBuf::from(".")).join(APP)
}

fn dir_from(env: &str, config: bool) -> PathBuf {
    let path = std::env::var_os(env).map(PathBuf::from).unwrap_or_else(|| default_dir(config));
    let _ = std::fs::create_dir_all(&path);
    path
}

pub fn config_dir() -> PathBuf {
    dir_from("DROVER_CONFIG_DIR", true)
}

pub fn state_dir() -> PathBuf {
    dir_from("DROVER_STATE_DIR", false)
}

pub fn daemon_info_file() -> PathBuf {
    state_dir().join("daemon.json")
}

pub fn session_file() -> PathBuf {
    state_dir().join("session.json")
}

pub fn log_dir() -> PathBuf {
    let path = state_dir().join("logs");
    let _ = std::fs::create_dir_all(&path);
    path
}

pub fn user_rules_dir() -> PathBuf {
    let path = config_dir().join("rules");
    let _ = std::fs::create_dir_all(&path);
    path
}

/// Root of the web assets: `DROVER_WEB_DIR`, else the repo's `src/drover` next to the source tree (dev builds),
/// else the folder of the executable. Holds `web/` (static runtime files) and `web_dist/` (built React UI).
pub fn web_root() -> PathBuf {
    if let Some(dir) = std::env::var_os("DROVER_WEB_DIR") {
        return PathBuf::from(dir);
    }
    let dev = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../src/drover");
    if dev.join("web").is_dir() {
        return dev;
    }
    std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf)).unwrap_or_default()
}

/// Make a secret file readable by the current user only (best effort).
pub fn restrict_to_owner(path: &Path) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
    }
    #[cfg(windows)]
    {
        let user = std::env::var("USERNAME").unwrap_or_default();
        let _ = std::process::Command::new("icacls")
            .arg(path)
            .args(["/inheritance:r", "/grant:r", &format!("{user}:F")])
            .output();
    }
}
