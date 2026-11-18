//! Real PTY round trips through PaneSession (no mocks).

use std::sync::mpsc;
use std::time::{Duration, Instant};

use super::*;

fn env() -> Vec<(String, String)> {
    vec![("PATH".into(), std::env::var("PATH").unwrap_or_default()), ("TERM".into(), "xterm-256color".into())]
}

fn pane(id: &str) -> Arc<PaneSession> {
    let meta = PaneMeta { id: id.into(), name: "t".into(), kind: "shell".into(), cwd: "/tmp".into(), ..Default::default() };
    PaneSession::new(meta, 80, 24, 1000)
}

fn wait_until(what: &str, mut cond: impl FnMut() -> bool) {
    let deadline = Instant::now() + Duration::from_secs(10);
    while !cond() {
        assert!(Instant::now() < deadline, "timed out waiting for {what}");
        std::thread::sleep(Duration::from_millis(20));
    }
}

#[test]
fn output_reaches_listener_replay_and_screen() {
    let p = pane("%1");
    let (tx, rx) = mpsc::channel::<(String, String)>();
    let tx = Mutex::new(tx);
    p.add_output_listener(move |id, data| {
        let _ = tx.lock().unwrap().send((id.into(), data.into()));
    });
    let argv = ["sh".to_string(), "-c".into(), "printf 'hello pane\\n'; sleep 0.2".into()];
    p.start(&argv, &env()).unwrap();
    wait_until("exit", || !p.alive() && p.state.lock().unwrap().exit_code.is_some());
    let (id, _) = rx.recv_timeout(Duration::from_secs(5)).unwrap();
    assert_eq!(id, "%1");
    assert!(p.replay_text().contains("hello pane"));
    assert!(p.state.lock().unwrap().screen.read_text(None).contains("hello pane"));
    assert_eq!(p.state_name(), "exited");
    assert_eq!(p.to_json()["exit_code"], 0);
}

#[test]
fn osc7501_report_reaches_tracker_and_exit_hook_fires() {
    let p = pane("%2");
    let (tx, rx) = mpsc::channel::<String>();
    let tx = Mutex::new(tx);
    p.set_exit_hook(move |pane| {
        let _ = tx.lock().unwrap().send(pane.id());
    });
    let argv = ["sh".to_string(), "-c".into(), "printf '\\033]7501;state=blocked\\007'; sleep 0.2".into()];
    p.start(&argv, &env()).unwrap();
    assert_eq!(rx.recv_timeout(Duration::from_secs(10)).unwrap(), "%2");
    assert_eq!(p.state.lock().unwrap().tracker.reported.as_deref(), Some("blocked"));
}

#[test]
fn resize_is_clamped_and_reaches_the_program() {
    let p = pane("%3");
    p.start(&["sh".to_string()], &env()).unwrap();
    p.resize(5, 1000);
    let size = {
        let st = p.state.lock().unwrap();
        (st.cols, st.rows)
    };
    assert_eq!(size, (10, 300));
    p.resize(100, 30);
    p.write("stty size\r");
    wait_until("stty size output", || p.state.lock().unwrap().screen.read_text(None).contains("30 100"));
    p.kill(true);
    wait_until("exit", || !p.alive());
}

#[test]
fn foreground_pgid_follows_the_running_program() {
    let p = pane("%4");
    p.start(&["sh".to_string()], &env()).unwrap();
    wait_until("shell pgid", || p.foreground_pgid().is_some());
    let shell = p.foreground_pgid();
    p.write("sleep 5\r");
    wait_until("sleep in foreground", || p.foreground_pgid().is_some() && p.foreground_pgid() != shell);
    p.kill(true);
}
