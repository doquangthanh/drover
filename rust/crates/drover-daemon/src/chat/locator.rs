//! Where is the user's `claude`? Port of `claude_locator.py` plus the search claude_agent_sdk does itself: PATH,
//! then the usual install folders. On Windows only a native claude.exe will do; an npm install puts a `claude.cmd`
//! shim on PATH with the real program inside the npm package next to it (a .cmd would need cmd.exe: never).

use std::path::{Path, PathBuf};

const NPM_PACKAGE_EXE: &str = "node_modules/@anthropic-ai/claude-code/bin/claude.exe";

pub fn find_claude() -> Option<PathBuf> {
    find_in(&std::env::var("PATH").unwrap_or_default(), &dirs::home_dir().unwrap_or_default())
}

fn find_in(path_env: &str, home: &Path) -> Option<PathBuf> {
    let windows = cfg!(windows);
    for entry in std::env::split_paths(path_env) {
        if !entry.is_absolute() {
            continue;
        }
        let exe = entry.join(if windows { "claude.exe" } else { "claude" });
        if exe.is_file() {
            return Some(exe);
        }
        if windows && entry.join("claude.cmd").is_file() && entry.join(NPM_PACKAGE_EXE).is_file() {
            return Some(entry.join(NPM_PACKAGE_EXE));
        }
    }
    let known: Vec<PathBuf> = if windows {
        vec![home.join(".local/bin/claude.exe")]
    } else {
        vec![home.join(".npm-global/bin/claude"), PathBuf::from("/usr/local/bin/claude"), home.join(".local/bin/claude"),
             home.join("node_modules/.bin/claude"), home.join(".yarn/bin/claude"), home.join(".claude/local/claude")]
    };
    known.into_iter().find(|p| p.is_file())
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    #[test]
    fn path_first_then_known_folders_and_relative_entries_are_ignored() {
        let root = std::env::temp_dir().join(format!("drover-locator-{}", crate::chat::new_id()));
        let (bin, home) = (root.join("bin"), root.join("home"));
        std::fs::create_dir_all(&bin).unwrap();
        std::fs::create_dir_all(home.join(".local/bin")).unwrap();
        assert_eq!(find_in("relative:", &home), None);
        std::fs::write(home.join(".local/bin/claude"), "").unwrap();
        assert_eq!(find_in(bin.to_str().unwrap(), &home), Some(home.join(".local/bin/claude")));
        std::fs::write(bin.join("claude"), "").unwrap();
        assert_eq!(find_in(bin.to_str().unwrap(), &home), Some(bin.join("claude")));
        let _ = std::fs::remove_dir_all(root);
    }
}
