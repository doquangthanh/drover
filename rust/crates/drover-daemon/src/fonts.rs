//! The font the user's own terminal uses, and installed monospace fonts. Port of `system_terminal_font.py`.

use std::process::Command;
use std::sync::OnceLock;

use serde_json::{Value, json};

fn gsettings(schema: &str, key: &str) -> Option<String> {
    let out = Command::new("gsettings").args(["get", schema, key]).output().ok()?;
    if !out.status.success() {
        return None;
    }
    let v = String::from_utf8_lossy(&out.stdout).trim().trim_matches(|c| c == '\'' || c == '"').to_string();
    (!v.is_empty()).then_some(v)
}

/// 'Ubuntu Mono 13' -> ('Ubuntu Mono', Some(13.0)); 'Monospace' -> ('Monospace', None).
pub fn parse_pango_font(desc: &str) -> (String, Option<f64>) {
    let desc = desc.trim();
    match desc.rsplit_once(char::is_whitespace) {
        Some((family, size)) if !family.trim().is_empty() => match size.parse::<f64>() {
            Ok(pt) => (family.trim().to_string(), Some(pt)),
            Err(_) => (desc.to_string(), None),
        },
        _ => (desc.to_string(), None),
    }
}

/// Windows Terminal's default profile font (`profiles.defaults.font`), its own default when unset. None when
/// Windows Terminal isn't installed. Its settings.json may hold `//` comment lines, dropped before parsing.
fn windows_terminal_font() -> Option<(String, Option<f64>)> {
    let local = std::env::var_os("LOCALAPPDATA")?;
    let file = std::path::Path::new(&local)
        .join(r"Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json");
    let text = std::fs::read_to_string(file).ok()?;
    let json: String = text.lines().filter(|l| !l.trim_start().starts_with("//")).collect::<Vec<_>>().join("\n");
    let v: Value = serde_json::from_str(&json).unwrap_or_default();
    let d = &v["profiles"]["defaults"];
    let face = d["font"]["face"].as_str().or(d["fontFace"].as_str()).unwrap_or("Cascadia Mono");
    let size = d["font"]["size"].as_f64().or(d["fontSize"].as_f64()).unwrap_or(12.0);
    Some((face.to_string(), Some(size)))
}

fn system_terminal_font() -> Option<(String, Option<f64>)> {
    if cfg!(windows) {
        return windows_terminal_font();
    }
    if !cfg!(target_os = "linux") || crate::launch::which("gsettings").is_none() {
        return None;
    }
    let mut desc = None;
    if let Some(uuid) = gsettings("org.gnome.Terminal.ProfilesList", "default") {
        let schema = format!("org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{uuid}/");
        if gsettings(&schema, "use-system-font").as_deref() == Some("false") {
            desc = gsettings(&schema, "font");
        }
    }
    let desc = desc.or_else(|| gsettings("org.gnome.desktop.interface", "monospace-font-name"))?;
    Some(parse_pango_font(&desc))
}

/// {family, size in CSS px} of the system terminal; empty / 0 when unknown. Cached: gsettings runs once.
pub fn default_terminal_font() -> Value {
    static CACHE: OnceLock<Value> = OnceLock::new();
    CACHE
        .get_or_init(|| {
            let (family, pt) = system_terminal_font().unwrap_or_default();
            json!({"family": family, "size": pt.map(|p| (p * 96.0 / 72.0).round() as i64).unwrap_or(0)})
        })
        .clone()
}

/// Monospace font families from fontconfig (fc-list); empty elsewhere.
pub fn installed_monospace_fonts() -> Vec<String> {
    let Ok(out) = Command::new("fc-list").args([":spacing=mono", "family"]).output() else { return vec![] };
    let mut names: Vec<String> = String::from_utf8_lossy(&out.stdout)
        .lines()
        .map(|l| l.split(',').next().unwrap_or("").trim().to_string())
        .filter(|n| !n.is_empty() && !n.to_lowercase().contains("emoji"))
        .collect();
    names.sort();
    names.dedup();
    names
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pango_font_parsing() {
        assert_eq!(parse_pango_font("Ubuntu Mono 13"), ("Ubuntu Mono".into(), Some(13.0)));
        assert_eq!(parse_pango_font("Monospace"), ("Monospace".into(), None));
        assert_eq!(parse_pango_font("Fira Code 10.5"), ("Fira Code".into(), Some(10.5)));
    }
}
