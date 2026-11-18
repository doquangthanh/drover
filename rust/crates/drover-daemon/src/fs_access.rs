//! File access for the folder picker and the Files view, only inside allowed roots / the space's folder.
//! Ports of `folder_browser.py` and `space_files.py`.

use std::path::{Component, Path, PathBuf};
use std::time::UNIX_EPOCH;

use serde_json::{Value, json};

const MAX_BYTES: u64 = 1_000_000; // larger files are cut here and flagged `truncated`
const MAX_WRITE_BYTES: usize = 5_000_000;
const MAX_ENTRIES: usize = 3000;

/// `Path.expanduser().resolve()`: `..` folded, symlinks of the existing part followed, the rest kept.
pub fn resolve(path: &Path) -> PathBuf {
    let path = match path.strip_prefix("~") {
        Ok(rest) => dirs::home_dir().unwrap_or_default().join(rest),
        Err(_) => path.to_path_buf(),
    };
    let path = if path.is_absolute() { path } else { std::env::current_dir().unwrap_or_default().join(path) };
    let mut out = PathBuf::new();
    for c in path.components() {
        match c {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other),
        }
    }
    let mut existing = out.clone();
    let mut rest = vec![];
    while !existing.exists() {
        match (existing.file_name().map(|n| n.to_os_string()), existing.parent().map(Path::to_path_buf)) {
            (Some(name), Some(parent)) => {
                rest.push(name);
                existing = parent;
            }
            _ => break,
        }
    }
    let mut base = std::fs::canonicalize(&existing).unwrap_or(existing);
    for name in rest.into_iter().rev() {
        base.push(name);
    }
    #[cfg(windows)]
    let base = PathBuf::from(base.to_string_lossy().trim_start_matches(r"\\?\"));
    base
}

fn inside(path: &Path, roots: &[PathBuf]) -> bool {
    roots.iter().any(|r| path.starts_with(r))
}

fn mtime_secs(m: &std::fs::Metadata) -> f64 {
    m.modified().ok().and_then(|t| t.duration_since(UNIX_EPOCH).ok()).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

pub fn allowed_roots(configured: &[String]) -> Vec<PathBuf> {
    let roots: Vec<PathBuf> = configured.iter().filter(|r| !r.is_empty()).map(PathBuf::from).collect();
    let roots = if roots.is_empty() { vec![dirs::home_dir().unwrap_or_default()] } else { roots };
    roots.iter().map(|r| resolve(r)).filter(|r| r.exists()).collect()
}

/// Sub-folders of `path` (folder picker), refusing anything outside the roots.
pub fn list_dirs(path: &str, configured: &[String], show_hidden: bool) -> Result<Value, String> {
    let roots = allowed_roots(configured);
    if roots.is_empty() {
        return Err("none of the folders in settings fs_roots exist".into());
    }
    let target = if path.is_empty() { roots[0].clone() } else { resolve(Path::new(path)) };
    if !inside(&target, &roots) {
        return Err(format!("{} is outside the folders drover may browse (settings: fs_roots)", target.display()));
    }
    if !target.is_dir() {
        return Err(format!("not a folder: {}", target.display()));
    }
    let read = std::fs::read_dir(&target).map_err(|_| format!("no permission to read {}", target.display()))?;
    let mut entries: Vec<Value> = read.flatten().filter_map(|e| {
        let is_dir = e.file_type().ok()?.is_dir(); // not following symlinks, like scandir
        let name = e.file_name().to_string_lossy().into_owned();
        let hidden = name.starts_with('.');
        if !is_dir || (hidden && !show_hidden) {
            return None;
        }
        let p = e.path();
        Some(json!({"name": name, "path": p.to_string_lossy(), "is_git": p.join(".git").exists(),
            "mtime": e.metadata().map(|m| mtime_secs(&m)).unwrap_or(0.0), "hidden": hidden}))
    }).collect();
    entries.sort_by_key(|e| e["name"].as_str().unwrap_or("").to_lowercase());
    entries.truncate(1000);
    let parent = target.parent().filter(|p| *p != target && inside(p, &roots)).map(|p| p.to_string_lossy().into_owned());
    Ok(json!({"path": target.to_string_lossy(), "parent": parent,
        "roots": roots.iter().map(|r| r.to_string_lossy()).collect::<Vec<_>>(), "entries": entries}))
}

pub fn make_dir(parent: &str, name: &str, configured: &[String]) -> Result<String, String> {
    if name.is_empty() || name.chars().any(|c| "\\/:*?\"<>|".contains(c)) || name == "." || name == ".." {
        return Err("invalid folder name".into());
    }
    let listed = list_dirs(parent, configured, false)?;
    let target = PathBuf::from(listed["path"].as_str().unwrap_or("")).join(name);
    std::fs::create_dir(&target).map_err(|e| if e.kind() == std::io::ErrorKind::AlreadyExists {
        format!("[Errno 17] File exists: '{}'", target.display())
    } else { e.to_string() })?;
    Ok(target.to_string_lossy().into_owned())
}

/// `root/rel` resolved; refuses `..` and symlinks that lead outside the space.
pub fn resolve_inside(root: &str, rel: &str) -> Result<(PathBuf, PathBuf), String> {
    let base = resolve(Path::new(root));
    let target = if rel.is_empty() { base.clone() } else { resolve(&base.join(rel)) };
    if !target.starts_with(&base) {
        return Err("path is outside this space".into());
    }
    Ok((base, target))
}

fn rel_of(base: &Path, path: &Path) -> String {
    path.strip_prefix(base).map(|p| p.to_string_lossy().replace('\\', "/")).unwrap_or_default()
}

pub fn list_dir(root: &str, rel: &str) -> Result<Value, String> {
    let (base, target) = resolve_inside(root, rel)?;
    let shown = if rel.is_empty() { "." } else { rel };
    if !target.is_dir() {
        return Err(format!("not a folder: {shown}"));
    }
    let read = std::fs::read_dir(&target).map_err(|_| format!("no permission to read {shown}"))?;
    let mut entries: Vec<Value> = read.flatten().filter(|e| e.file_name() != ".git").map(|e| {
        let is_dir = e.file_type().map(|t| t.is_dir()).unwrap_or(false);
        let size = if is_dir { 0 } else { e.metadata().map(|m| m.len()).unwrap_or(0) };
        json!({"name": e.file_name().to_string_lossy(), "path": rel_of(&base, &e.path()), "dir": is_dir, "size": size})
    }).collect();
    entries.sort_by_key(|e| (!e["dir"].as_bool().unwrap_or(false), e["name"].as_str().unwrap_or("").to_lowercase()));
    let truncated = entries.len() > MAX_ENTRIES;
    entries.truncate(MAX_ENTRIES);
    Ok(json!({"path": rel, "entries": entries, "truncated": truncated}))
}

/// Modification time in microseconds: still exact when JSON turns it into a JS number.
fn mtime_us(path: &Path) -> i64 {
    std::fs::metadata(path).ok().and_then(|m| m.modified().ok()).and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_micros() as i64).unwrap_or(0)
}

pub fn read_text(root: &str, rel: &str) -> Result<Value, String> {
    let (_, target) = resolve_inside(root, rel)?;
    if !target.is_file() {
        return Err(format!("not a file: {rel}"));
    }
    let size = std::fs::metadata(&target).map(|m| m.len()).map_err(|e| e.to_string())?;
    let mut data = Vec::new();
    use std::io::Read;
    std::fs::File::open(&target).and_then(|f| f.take(MAX_BYTES).read_to_end(&mut data)).map_err(|e| e.to_string())?;
    if data[..data.len().min(8192)].contains(&0) {
        return Ok(json!({"path": rel, "binary": true, "size": size}));
    }
    let truncated = size > MAX_BYTES;
    let (text, lossy) = match String::from_utf8(data) {
        Ok(t) => (t, false),
        Err(e) => (String::from_utf8_lossy(e.as_bytes()).into_owned(), true),
    };
    let lines = text.matches('\n').count() + usize::from(!text.ends_with('\n') && !text.is_empty());
    // Saving a cut-off or lossily decoded file would destroy data, so those open read-only.
    let why = if truncated { "larger than 1 MB" } else if lossy { "not UTF-8 text" } else { "" };
    Ok(json!({"path": rel, "binary": false, "size": size, "truncated": truncated, "text": text, "lines": lines,
        "mtime_us": mtime_us(&target), "editable": !(truncated || lossy), "why_readonly": why}))
}

/// Save `text` into the space. Atomic (temp file + rename). Git internals are never writable.
pub fn write_text(root: &str, rel: &str, text: &str, base_mtime_us: Option<i64>, create: bool, force: bool) -> Result<Value, String> {
    let (base, target) = resolve_inside(root, rel)?;
    let in_git = target.strip_prefix(&base).map(|r| r.components().any(|c| c.as_os_str().to_string_lossy().to_lowercase() == ".git")).unwrap_or(true);
    if rel.is_empty() || in_git {
        return Err("this path cannot be written".into());
    }
    if text.len() > MAX_WRITE_BYTES {
        return Err("file is too large to save from the editor".into());
    }
    if create {
        if target.exists() {
            return Err(format!("already exists: {rel}"));
        }
        if let Some(dir) = target.parent() {
            std::fs::create_dir_all(dir).map_err(|e| e.to_string())?;
        }
    } else {
        if !target.is_file() {
            return Err(format!("not a file: {rel}"));
        }
        if !force && base_mtime_us.is_some_and(|b| b != mtime_us(&target)) {
            return Err("File changed on disk since you opened it (an agent may have edited it).".into());
        }
    }
    let name = target.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let tmp = target.with_file_name(format!(".{name}.drover-tmp"));
    let result = std::fs::write(&tmp, text.as_bytes())
        .and_then(|_| if create { Ok(()) } else { std::fs::metadata(&target).and_then(|m| std::fs::set_permissions(&tmp, m.permissions())) })
        .and_then(|_| std::fs::rename(&tmp, &target));
    let _ = std::fs::remove_file(&tmp);
    result.map_err(|e| e.to_string())?;
    Ok(json!({"mtime_us": mtime_us(&target), "size": text.len()}))
}
