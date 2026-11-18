//! One version for both daemons during the move: read it from the Python package's pyproject.toml.
fn main() {
    let pyproject = concat!(env!("CARGO_MANIFEST_DIR"), "/../../../pyproject.toml");
    println!("cargo:rerun-if-changed={pyproject}");
    let version = std::fs::read_to_string(pyproject)
        .ok()
        .and_then(|t| t.lines().find_map(|l| l.strip_prefix("version = ").map(|v| v.trim().trim_matches('"').to_string())))
        .unwrap_or_else(|| std::env::var("CARGO_PKG_VERSION").unwrap_or_default());
    println!("cargo:rustc-env=DROVER_VERSION={version}");
}
