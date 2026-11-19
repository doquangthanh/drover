//! Windows release: this daemon is `<state>/runtime/<version>/dr.exe`, installed by drover.exe (Python window +
//! CLI), whose path is in the runtime's `.complete` marker. Updating means swapping that drover.exe, which stays
//! Python's job (`drover.exe self-update <tag>`); the restart then goes through the new drover.exe, which starts
//! the new version's daemon (see `restart_command`).

use std::path::PathBuf;

/// The drover.exe that installed this runtime, if it still exists.
pub fn owner_exe() -> Option<PathBuf> {
    let marker = std::env::current_exe().ok()?.with_file_name(".complete");
    let owner = PathBuf::from(std::fs::read_to_string(marker).ok()?.trim());
    owner.is_file().then_some(owner)
}

pub fn installable() -> bool {
    owner_exe().is_some()
}

pub async fn apply(tag: &str) -> Result<(), String> {
    let owner = owner_exe().ok_or("this install can't update itself; download the new drover.exe")?;
    if !crate::self_update_apply::tag_ok(tag) {
        return Err("bad version tag".into());
    }
    let mut cmd = tokio::process::Command::new(&owner);
    cmd.args(["self-update", tag]).stdin(std::process::Stdio::null()).kill_on_drop(true);
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let out = cmd.output().await.map_err(|e| format!("could not run {}: {e}", owner.display()))?;
    if out.status.success() {
        return Ok(());
    }
    let err = String::from_utf8_lossy(&out.stderr);
    let err = err.trim().trim_start_matches("error: ");
    Err(if err.is_empty() { format!("update failed (exit {:?})", out.status.code()) } else { err.to_string() })
}

/// Program for the restart after an update: the (now new) drover.exe, else this binary.
pub fn restart_command() -> Option<PathBuf> {
    owner_exe().or_else(|| std::env::current_exe().ok())
}
