//! Replace the release bundle (Linux `~/.local/share/drover`, Windows `%LOCALAPPDATA%\drover\app`: Rust `dr`,
//! Python `dr-py`, Rust `drover`) with release `tag`: download, verify its SHA-256 against the release's `.sha256`
//! file, unpack next to the bundle and swap (renames on one filesystem; the old copy is put back if the swap fails).
//! Same code on every OS; only the archive type and the swap step differ (Windows can't rename a folder that holds
//! a running program, but can rename the program itself).

use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use sha2::{Digest, Sha256};

use crate::self_update::{REPO, curl};

const DR: &str = if cfg!(windows) { "dr.exe" } else { "dr" };
const OS: &str = if cfg!(windows) { "windows" } else { "linux" };
const ARCHIVE: &str = if cfg!(windows) { "zip" } else { "tar.gz" };

/// The release bundle this binary runs from: a folder with `dr` and the Python `_internal/` next to it. Found once,
/// at the first call: after an update swapped it, the running exe has moved but the bundle path stays right.
pub fn bundle_dir() -> Option<PathBuf> {
    static DIR: OnceLock<Option<PathBuf>> = OnceLock::new();
    DIR.get_or_init(|| {
        let dir = std::env::current_exe().ok()?.canonicalize().ok()?.parent()?.to_path_buf();
        #[cfg(windows)]
        let dir = PathBuf::from(dir.to_string_lossy().trim_start_matches(r"\\?\"));
        (dir.join(DR).is_file() && dir.join("_internal").is_dir()).then_some(dir)
    })
    .clone()
}

pub fn installable() -> bool {
    bundle_dir().is_some()
}

/// The bundle's daemon, for the restart after an update.
pub fn restart_command() -> Option<PathBuf> {
    bundle_dir().map(|d| d.join(DR))
}

fn arch() -> Result<&'static str, String> {
    match std::env::consts::ARCH {
        "x86_64" => Ok("x64"),
        "aarch64" => Ok("arm64"),
        other => Err(format!("unsupported CPU {other}")),
    }
}

pub(crate) fn tag_ok(tag: &str) -> bool {
    tag.strip_prefix('v').is_some_and(|v| !v.is_empty() && v.split('.').all(|n| !n.is_empty() && n.chars().all(|c| c.is_ascii_digit())))
}

/// `sha256sum` output ("<hex>  <name>") or a bare hex digest.
pub fn checksum_matches(file: &Path, sums: &str) -> Result<bool, String> {
    let want = sums.split_whitespace().next().unwrap_or_default().to_ascii_lowercase();
    let data = std::fs::read(file).map_err(|e| e.to_string())?;
    let got: String = Sha256::digest(&data).iter().map(|b| format!("{b:02x}")).collect();
    Ok(want.len() == 64 && got == want)
}

pub async fn apply(tag: &str) -> Result<(), String> {
    let target = bundle_dir().ok_or("this install can't update itself; re-run the install script")?;
    if !tag_ok(tag) {
        return Err("bad version tag".into());
    }
    let asset = format!("drover-{OS}-{}.{ARCHIVE}", arch()?);
    let url = format!("https://github.com/{REPO}/releases/download/{tag}/{asset}");
    let parent = target.parent().ok_or("bundle has no parent folder")?;
    remove_leftovers(parent);
    // Same filesystem as the bundle, so the renames below are atomic.
    let tmp = parent.join(format!(".drover-update-{}", crate::chat::new_id()));
    std::fs::create_dir_all(tmp.join("new")).map_err(|e| e.to_string())?;
    let result = install_into(&target, &tmp, &url).await;
    let _ = std::fs::remove_dir_all(&tmp);
    result
}

async fn install_into(target: &Path, tmp: &Path, url: &str) -> Result<(), String> {
    let archive = tmp.join(format!("drover.{ARCHIVE}"));
    let archive_s = archive.to_string_lossy().to_string();
    curl(&["-f", "--max-time", "600", "-o", &archive_s, url]).await.map_err(|e| format!("download failed: {e}"))?;
    let sums = curl(&["-f", &format!("{url}.sha256")]).await
        .map_err(|_| "the release has no checksum file; not installing an unverified download".to_string())?;
    if !checksum_matches(&archive, &sums)? {
        return Err("downloaded archive does not match its checksum".into());
    }
    // tar reads both: GNU tar gunzips, Windows 10+ ships bsdtar, which unpacks zip.
    let mut tar = tokio::process::Command::new("tar");
    tar.arg("-xf").arg(&archive).arg("-C").arg(tmp.join("new")).kill_on_drop(true);
    #[cfg(windows)]
    tar.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    let out = tar.output().await.map_err(|e| format!("could not run tar: {e}"))?;
    if !out.status.success() {
        return Err(format!("could not unpack the archive: {}", String::from_utf8_lossy(&out.stderr).trim()));
    }
    let fresh = tmp.join("new").join("drover");
    if !fresh.join(DR).is_file() || !fresh.join("_internal").is_dir() {
        return Err(format!("downloaded archive is missing drover/{DR}"));
    }
    swap(target, &fresh, &tmp.join("old"))
}

/// Update folders an earlier update could not delete (Windows: the old daemon was still running from them).
fn remove_leftovers(parent: &Path) {
    for entry in std::fs::read_dir(parent).into_iter().flatten().flatten() {
        if entry.file_name().to_string_lossy().starts_with(".drover-update-") {
            let _ = std::fs::remove_dir_all(entry.path());
        }
    }
}

/// target -> old, fresh -> target; on failure the old copy goes back.
#[cfg(not(windows))]
pub fn swap(target: &Path, fresh: &Path, old: &Path) -> Result<(), String> {
    std::fs::rename(target, old).map_err(|e| format!("could not move the current install aside: {e}"))?;
    if let Err(e) = std::fs::rename(fresh, target) {
        let _ = std::fs::rename(old, target);
        return Err(format!("could not install the new version: {e}"));
    }
    Ok(())
}

/// Windows: the folder can't move while dr.exe runs from it, so move its entries one by one (a running exe can
/// be renamed). Any failure (a DLL held open, e.g. by a `dr tui`) puts every entry back where it was.
#[cfg(windows)]
pub fn swap(target: &Path, fresh: &Path, old: &Path) -> Result<(), String> {
    fn names(dir: &Path) -> Result<Vec<std::ffi::OsString>, String> {
        Ok(std::fs::read_dir(dir).map_err(|e| e.to_string())?.flatten().map(|e| e.file_name()).collect())
    }
    /// Move `names` from `from` to `to`; on failure move the ones already moved back and report.
    fn move_all(names: &[std::ffi::OsString], from: &Path, to: &Path) -> Result<(), std::io::Error> {
        for (i, name) in names.iter().enumerate() {
            if let Err(e) = std::fs::rename(from.join(name), to.join(name)) {
                for done in &names[..i] {
                    let _ = std::fs::rename(to.join(done), from.join(done));
                }
                return Err(e);
            }
        }
        Ok(())
    }
    let incoming = names(fresh)?; // before anything moves: a missing download leaves the install untouched
    let current = names(target)?;
    std::fs::create_dir_all(old).map_err(|e| e.to_string())?;
    move_all(&current, target, old).map_err(|e| format!("could not move the current install aside (close `dr tui` and other drover programs, then try again): {e}"))?;
    if let Err(e) = move_all(&incoming, fresh, target) {
        let _ = move_all(&current, old, target);
        return Err(format!("could not install the new version: {e}"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tags_checksums_and_swap() {
        assert!(tag_ok("v0.1.33") && tag_ok("v1") && !tag_ok("0.1") && !tag_ok("v0..1") && !tag_ok("v1;rm") && !tag_ok("v"));
        let root = std::env::temp_dir().join(format!("drover-swap-{}", crate::chat::new_id()));
        let (target, fresh, old) = (root.join("drover"), root.join("new"), root.join("old"));
        std::fs::create_dir_all(&target).unwrap();
        std::fs::create_dir_all(&fresh).unwrap();
        std::fs::write(target.join("v"), "1").unwrap();
        std::fs::write(fresh.join("v"), "2").unwrap();
        // sha256("2")
        let sum = "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35  drover-linux-x64.tar.gz";
        assert!(checksum_matches(&fresh.join("v"), sum).unwrap());
        assert!(!checksum_matches(&target.join("v"), sum).unwrap());
        assert!(!checksum_matches(&fresh.join("v"), "short").unwrap());
        swap(&target, &fresh, &old).unwrap();
        assert_eq!(std::fs::read_to_string(target.join("v")).unwrap(), "2");
        assert_eq!(std::fs::read_to_string(old.join("v")).unwrap(), "1");
        // A failed second step puts the working copy back.
        assert!(swap(&target, &root.join("missing"), &root.join("old2")).is_err());
        assert_eq!(std::fs::read_to_string(target.join("v")).unwrap(), "2");
        let _ = std::fs::remove_dir_all(root);
    }
}
