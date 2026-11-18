//! Plain data of a pane: launch metadata and mutable runtime state (guarded by PaneSession's mutexes).

use std::collections::VecDeque;

use crate::screen::PaneScreen;
use crate::status_tracker::StatusTracker;

/// Raw output kept for re-attaching clients (bytes of UTF-8; Python counted characters).
pub const REPLAY_LIMIT: usize = 512 * 1024;

#[derive(Debug, Clone, Default)]
pub struct PaneMeta {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub command: String,
    pub argv: Vec<String>,
    pub cwd: String,
    pub space_id: String,
    pub tab_id: String,
    pub parent: Option<String>,
    pub created_at: f64,
    pub resume: String,
}

pub struct PaneState {
    pub screen: PaneScreen,
    pub tracker: StatusTracker,
    pub(crate) replay: VecDeque<String>,
    pub(crate) replay_size: usize,
    pub last_output_at: f64,
    /// Last output that changed visible text (not just terminal modes).
    pub screen_changed_at: f64,
    pub dirty: bool,
    pub unread: bool,
    pub exit_code: Option<i32>,
    pub focused: bool,
    pub cols: u16,
    pub rows: u16,
    /// After a scrolling read, until its redraws age out.
    pub detection_paused_until: f64,
    /// Started as a shell: its kind follows the foreground program.
    pub shell_launched: bool,
    pub fg_pgid: Option<i32>,
    pub fg_checked_at: f64,
    pub claude_checked_at: f64,
}

impl PaneState {
    pub fn new(cols: u16, rows: u16, history: usize) -> Self {
        PaneState {
            screen: PaneScreen::new(cols as usize, rows as usize, history),
            tracker: StatusTracker::default(),
            replay: VecDeque::new(),
            replay_size: 0,
            last_output_at: 0.0,
            screen_changed_at: 0.0,
            dirty: false,
            unread: false,
            exit_code: None,
            focused: false,
            cols,
            rows,
            detection_paused_until: 0.0,
            shell_launched: false,
            fg_pgid: None,
            fg_checked_at: 0.0,
            claude_checked_at: 0.0,
        }
    }
}
