//! Replace the Linux release bundle (`~/.local/share/drover`: Rust `dr` + Python `dr-py`, Rust `drover`) with
//! release `tag`: download, verify its SHA-256 against the release's `.sha256` file, unpack next to the bundle and
//! swap folders (atomic renames on one filesystem; the old copy is put back if the swap fails).

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::self_update::{REPO, curl};

/// The release bundle this binary runs from: a folder with `dr` and the Python `_internal/` next to it.
fn bundle_dir() -> Option<PathBuf> {
    let dir = std::env::current_exe().ok()?.canonicalize().ok()?.parent()?.to_path_buf();
    (dir.join("dr").is_file() && dir.join("_internal").is_dir()).then_some(dir)
}

pub fn installable() -> bool {
    cfg!(target_os = "linux") && bundle_dir().is_some()
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
    let target = bundle_dir().filter(|_| cfg!(target_os = "linux"))
        .ok_or("this install can't update itself; re-run the install script")?;
    if !tag_ok(tag) {
        return Err("bad version tag".into());
    }
    let asset = format!("drover-linux-{}.tar.gz", arch()?);
    let url = format!("https://github.com/{REPO}/releases/download/{tag}/{asset}");
    let parent = target.parent().ok_or("bundle has no parent folder")?;
    // Same filesystem as the bundle, so the renames below are atomic.
    let tmp = parent.join(format!(".drover-update-{}", crate::chat::new_id()));
    std::fs::create_dir_all(tmp.join("new")).map_err(|e| e.to_string())?;
    let result = install_into(&target, &tmp, &url).await;
    let _ = std::fs::remove_dir_all(&tmp);
    result
}

async fn install_into(target: &Path, tmp: &Path, url: &str) -> Result<(), String> {
    let archive = tmp.join("drover.tar.gz");
    let archive_s = archive.to_string_lossy().to_string();
    curl(&["-f", "--max-time", "600", "-o", &archive_s, url]).await.map_err(|e| format!("download failed: {e}"))?;
    let sums = curl(&["-f", &format!("{url}.sha256")]).await
        .map_err(|_| "the release has no checksum file; not installing an unverified download".to_string())?;
    if !checksum_matches(&archive, &sums)? {
        return Err("downloaded archive does not match its checksum".into());
    }
    let out = tokio::process::Command::new("tar").arg("-xzf").arg(&archive).arg("-C").arg(tmp.join("new"))
        .output().await.map_err(|e| format!("could not run tar: {e}"))?;
    if !out.status.success() {
        return Err(format!("could not unpack the archive: {}", String::from_utf8_lossy(&out.stderr).trim()));
    }
    let fresh = tmp.join("new").join("drover");
    if !fresh.join("dr").is_file() || !fresh.join("drover-server").is_file() {
        return Err("downloaded archive is missing drover/dr or drover/drover-server".into());
    }
    swap(target, &fresh, &tmp.join("old"))
}

/// target -> old, fresh -> target; on failure the old copy goes back.
pub fn swap(target: &Path, fresh: &Path, old: &Path) -> Result<(), String> {
    std::fs::rename(target, old).map_err(|e| format!("could not move the current install aside: {e}"))?;
    if let Err(e) = std::fs::rename(fresh, target) {
        let _ = std::fs::rename(old, target);
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
