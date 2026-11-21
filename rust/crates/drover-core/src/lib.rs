//! Drover core: pane model, terminal emulation, agent status detection, layout tree.

pub mod alt_screen_pages;
pub mod detection_rules;
pub mod draft;
pub mod foreground_probe;
pub mod keystroke_bytes;
pub mod launch_command;
pub mod layout_tree;
pub mod osc7501;
pub mod pane_session;
pub mod pane_state;
pub mod pty;
pub mod screen;
mod screen_snapshot;
pub mod status_detector;
pub mod status_tracker;
pub mod terminal_keys;
pub mod utf8_stream;
#[cfg(windows)]
mod windows_process_cwd;
#[cfg(windows)]
pub mod windows_process_env;
#[cfg(windows)]
pub mod windows_process_tree;
pub mod workspace_models;
