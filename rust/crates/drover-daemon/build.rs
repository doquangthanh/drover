//! One version for both daemons during the move: read it from the Python package's pyproject.toml.
//! The agent skill text (`skill.text`) also has one source: the Python module's AGENT_SKILL string.
fn main() {
    let pyproject = concat!(env!("CARGO_MANIFEST_DIR"), "/../../../pyproject.toml");
    println!("cargo:rerun-if-changed={pyproject}");
    let version = std::fs::read_to_string(pyproject)
        .ok()
        .and_then(|t| t.lines().find_map(|l| l.strip_prefix("version = ").map(|v| v.trim().trim_matches('"').to_string())))
        .unwrap_or_else(|| std::env::var("CARGO_PKG_VERSION").unwrap_or_default());
    println!("cargo:rustc-env=DROVER_VERSION={version}");

    let skill_py = concat!(env!("CARGO_MANIFEST_DIR"), "/../../../src/drover/skill/agent_skill_text.py");
    println!("cargo:rerun-if-changed={skill_py}");
    let source = std::fs::read_to_string(skill_py).expect("agent_skill_text.py");
    let text = source.split_once("AGENT_SKILL = \"\"\"").and_then(|(_, rest)| rest.split_once("\"\"\"")).map(|(t, _)| t)
        .expect("AGENT_SKILL = \"\"\"...\"\"\" in agent_skill_text.py");
    std::fs::write(format!("{}/agent_skill.md", std::env::var("OUT_DIR").unwrap()), text).unwrap();
}
