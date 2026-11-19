//! Hand a command to the Python CLI unchanged. Its exit code becomes ours. Lookup order:
//! `$DROVER_PYTHON_DR` (tests, source checkouts), `dr-py(.exe)` next to this binary (Windows runtime folder),
//! then the drover.exe named in the runtime's `.complete` marker (also a full CLI), so a runtime is never stuck.

use std::ffi::OsString;
use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};

const PYTHON_DR: &str = if cfg!(windows) { "dr-py.exe" } else { "dr-py" };

fn python_dr() -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("DROVER_PYTHON_DR").filter(|p| !p.is_empty()) {
        return Some(PathBuf::from(path));
    }
    let exe = std::env::current_exe().ok()?;
    let sibling = exe.with_file_name(PYTHON_DR);
    if sibling.is_file() {
        return Some(sibling);
    }
    let owner = std::fs::read_to_string(exe.with_file_name(".complete")).ok()?;
    let owner = PathBuf::from(owner.trim());
    owner.is_file().then_some(owner)
}

/// Run the Python `dr` with `args`. `stdin_bytes`: what the fast path already read from stdin (`dr prompt x -`),
/// fed to the child so it sees the same input.
pub fn run(args: &[OsString], stdin_bytes: Option<&[u8]>) -> i32 {
    let Some(program) = python_dr() else {
        eprintln!("error: {PYTHON_DR} is missing next to {}; reinstall drover", std::env::current_exe()
            .map(|p| p.display().to_string()).unwrap_or_else(|_| "dr".into()));
        return 1;
    };
    let mut cmd = Command::new(&program);
    cmd.args(args);
    if stdin_bytes.is_some() {
        cmd.stdin(Stdio::piped());
    }
    #[cfg(unix)]
    if stdin_bytes.is_none() {
        use std::os::unix::process::CommandExt;
        let err = cmd.exec(); // only returns on failure
        eprintln!("error: cannot run {}: {err}", program.display());
        return 1;
    }
    crate::ctrl_c_handling::ignore_while_child_runs(); // the child (same console) gets Ctrl+C and decides; we just wait for its exit code
    let mut child = match cmd.spawn() {
        Ok(child) => child,
        Err(err) => {
            eprintln!("error: cannot run {}: {err}", program.display());
            return 1;
        }
    };
    if let (Some(bytes), Some(mut pipe)) = (stdin_bytes, child.stdin.take()) {
        let _ = pipe.write_all(bytes); // dropped right after: the child sees EOF
    }
    match child.wait() {
        Ok(status) => status.code().unwrap_or(1),
        Err(_) => 1,
    }
}
