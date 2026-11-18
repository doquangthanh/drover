//! Is a newer drover release on GitHub, and install it. Port of `self_update.py` using the system `curl` (Linux,
//! macOS and Windows 10+ ship it), so no TLS stack is built into the daemon. `apply` (Linux release bundle only)
//! lives in `self_update_apply.rs`; Windows keeps the Python updater until its Rust build is tested.

use serde_json::{Value, json};

pub(crate) const REPO: &str = "doquangthanh/drover";
const TIMEOUT_SECS: &str = "15";

/// 'v0.1.5' -> [0, 1, 5]; anything non-numeric is ignored.
pub fn version_tuple(text: &str) -> Vec<u64> {
    let base = text.split('-').next().unwrap_or_default();
    base.split(|c: char| !c.is_ascii_digit()).filter(|n| !n.is_empty()).filter_map(|n| n.parse().ok()).collect()
}

pub use crate::self_update_apply::{apply, installable};

pub(crate) async fn curl(args: &[&str]) -> Result<String, String> {
    let mut cmd = tokio::process::Command::new("curl");
    cmd.args(["-sSL", "--max-time", TIMEOUT_SECS, "-A", "drover"]).args(args).kill_on_drop(true);
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000);
    let out = cmd.output().await.map_err(|e| format!("could not run curl: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).trim().to_string());
    }
    Ok(String::from_utf8_lossy(&out.stdout).to_string())
}

/// Fallback when the API refuses (60 calls/hour/IP): /releases/latest redirects to /tag/<tag>.
async fn latest_tag_from_redirect(api_error: &str) -> Result<String, String> {
    let page = format!("https://github.com/{REPO}/releases/latest");
    let out = curl(&["-I", "-o", if cfg!(windows) { "NUL" } else { "/dev/null" }, "-w", "%{url_effective}", &page]).await
        .map_err(|_| format!("could not reach GitHub: {api_error}"))?;
    let tag = out.trim().rsplit_once("/tag/").map(|(_, t)| t.to_string()).unwrap_or_default();
    if tag.starts_with('v') && tag[1..].chars().all(|c| c.is_ascii_digit() || c == '.') && tag.len() > 1 {
        Ok(tag)
    } else {
        Err(format!("could not reach GitHub: {api_error}"))
    }
}

pub async fn check() -> Result<Value, String> {
    let api = format!("https://api.github.com/repos/{REPO}/releases/latest");
    let data = match curl(&["-f", "-H", "Accept: application/vnd.github+json", &api]).await
        .and_then(|t| serde_json::from_str::<Value>(&t).map_err(|e| e.to_string()))
    {
        Ok(data) => data,
        Err(e) => {
            let tag = latest_tag_from_redirect(&e).await?;
            json!({"tag_name": tag, "html_url": format!("https://github.com/{REPO}/releases/tag/{tag}")})
        }
    };
    let tag = data["tag_name"].as_str().unwrap_or_default().to_string();
    let current = env!("DROVER_VERSION");
    Ok(json!({
        "current": current, "latest": tag.trim_start_matches('v'), "tag": tag, "url": data["html_url"].as_str().unwrap_or_default(),
        "notes": data["body"].as_str().unwrap_or_default().chars().take(4000).collect::<String>(),
        "available": !tag.is_empty() && version_tuple(&tag) > version_tuple(current),
        "installable": installable(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions_compare_by_number() {
        assert_eq!(version_tuple("v0.1.33"), [0, 1, 33]);
        assert_eq!(version_tuple("0.2.0-dev"), [0, 2, 0]);
        assert!(version_tuple("v0.1.10") > version_tuple("0.1.9"));
    }
}
