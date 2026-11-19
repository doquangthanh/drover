//! Drover folders, the same as `app_paths.py` / `drover-daemon` paths: `DROVER_STATE_DIR` / `DROVER_CONFIG_DIR`
//! override; Windows `%LOCALAPPDATA%\drover` for both; elsewhere the XDG state and config folders.

use std::path::PathBuf;

const APP: &str = "drover";

fn default_dir(config: bool) -> PathBuf {
    #[cfg(windows)]
    let base = {
        let _ = config;
        std::env::var_os("LOCALAPPDATA").map(PathBuf::from)
    };
    #[cfg(not(windows))]
    let base = if config { dirs::config_dir() } else { dirs::state_dir().or_else(dirs::data_local_dir) };
    base.unwrap_or_else(|| PathBuf::from(".")).join(APP)
}

fn dir_from(env: &str, config: bool) -> PathBuf {
    std::env::var_os(env).filter(|v| !v.is_empty()).map(PathBuf::from).unwrap_or_else(|| default_dir(config))
}

pub fn state_dir() -> PathBuf {
    dir_from("DROVER_STATE_DIR", false)
}

pub fn config_dir() -> PathBuf {
    dir_from("DROVER_CONFIG_DIR", true)
}
