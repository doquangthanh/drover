//! Files view data shared by native clients (`files.list` entries and `files.read` results).

use serde::Deserialize;

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct Entry {
    pub name: String,
    pub path: String,
    pub dir: bool,
}

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct FileContent {
    pub error: Option<String>,
    pub binary: bool,
    pub size: u64,
    pub text: Option<String>,
    pub mtime_us: i64,
}
