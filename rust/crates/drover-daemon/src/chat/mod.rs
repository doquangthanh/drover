//! Chat agents: a Claude conversation shown as a chat instead of a terminal. Port of `src/drover/chat/*`, talking to
//! the `claude` CLI's stream-json + stdio control protocol directly (what claude_agent_sdk does in Python).

pub mod cli_process;
pub mod file_search;
pub mod locator;
pub mod manager;
pub mod session;
mod session_permissions;
pub mod store;
pub mod transcript;

/// Random 10-hex-digit id (Python: `uuid4().hex[:10]`).
pub fn new_id() -> String {
    let mut bytes = [0u8; 5];
    getrandom::fill(&mut bytes).expect("os random");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
