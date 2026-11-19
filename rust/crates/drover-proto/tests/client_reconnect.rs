//! The client against a real daemon binary: connect, state, rpc, output, then the daemon restarts on a new port
//! and the client reconnects and re-attaches by itself.
//! Runs when DROVER_TEST_DAEMON_BIN points at a `dr` executable (e.g. rust/target/debug/dr); skipped otherwise.

use std::process::{Child, Command as Proc};
use std::sync::mpsc::channel;
use std::time::{Duration, Instant};

use drover_proto::client::{self, Command, Incoming};
use serde_json::json;

struct Daemon(Child);

impl Drop for Daemon {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn start_daemon(bin: &str, state: &std::path::Path) -> Daemon {
    let _ = std::fs::remove_file(state.join("daemon.json"));
    let child = Proc::new(bin).args(["server", "run"]).env("DROVER_STATE_DIR", state)
        .env("DROVER_CONFIG_DIR", state.join("config")).spawn().expect("start daemon");
    let deadline = Instant::now() + Duration::from_secs(15);
    while !state.join("daemon.json").exists() {
        assert!(Instant::now() < deadline, "daemon did not write daemon.json");
        std::thread::sleep(Duration::from_millis(50));
    }
    Daemon(child)
}

fn wait_for(rx: &std::sync::mpsc::Receiver<Incoming>, what: &str, ok: impl Fn(&Incoming) -> bool) -> Incoming {
    let deadline = Instant::now() + Duration::from_secs(20);
    loop {
        let left = deadline.saturating_duration_since(Instant::now());
        match rx.recv_timeout(left) {
            Ok(m) if ok(&m) => return m,
            Ok(_) => {}
            Err(_) => panic!("timed out waiting for {what}"),
        }
    }
}

#[test]
fn connects_calls_and_reconnects_after_a_daemon_restart() {
    let Ok(bin) = std::env::var("DROVER_TEST_DAEMON_BIN") else {
        eprintln!("skipped: set DROVER_TEST_DAEMON_BIN");
        return;
    };
    let dir = std::env::temp_dir().join(format!("drover-proto-test-{}", std::process::id()));
    std::fs::create_dir_all(dir.join("config")).unwrap();
    // SAFETY: set before the client thread starts; the test is single-threaded until then.
    unsafe { std::env::set_var("DROVER_STATE_DIR", &dir) };
    let daemon = start_daemon(&bin, &dir);

    let c = client::start(|| {});
    wait_for(&c.incoming, "Connected", |m| *m == Incoming::Connected);
    wait_for(&c.incoming, "state", |m| matches!(m, Incoming::Event { name, .. } if name == "state"));

    let (tx, rx) = channel();
    let cmd = "sh -c 'echo hello-native; sleep 60'";
    c.commands.send(Command::Rpc { method: "pane.create".into(),
        params: json!({"command": cmd, "cwd": dir.to_string_lossy(), "name": "probe"}), reply: Some(tx) }).unwrap();
    let pane = rx.recv_timeout(Duration::from_secs(10)).unwrap().expect("pane.create")["id"].as_str().unwrap().to_string();
    c.commands.send(Command::Attach(pane.clone())).unwrap();
    wait_for(&c.incoming, "output", |m| matches!(m, Incoming::Output { data, .. } if data.contains("hello-native")));

    drop(daemon); // the pane dies with it; the client must notice and keep trying
    wait_for(&c.incoming, "Disconnected", |m| matches!(m, Incoming::Disconnected(_)));
    let _daemon = start_daemon(&bin, &dir); // new port and token
    wait_for(&c.incoming, "Connected again", |m| *m == Incoming::Connected);
    wait_for(&c.incoming, "state again", |m| matches!(m, Incoming::Event { name, .. } if name == "state"));
    let _ = std::fs::remove_dir_all(&dir);
}
