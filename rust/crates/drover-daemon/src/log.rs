//! Minimal logger: daemon.log in the state dir (and stderr in the foreground). No logging framework needed.

use std::io::Write;
use std::sync::Mutex;
use std::sync::OnceLock;

struct Sink {
    file: Option<std::fs::File>,
    stderr: bool,
}

static SINK: OnceLock<Mutex<Sink>> = OnceLock::new();

pub fn init(foreground: bool) {
    let file =
        std::fs::OpenOptions::new().create(true).append(true).open(crate::paths::log_dir().join("daemon.log")).ok();
    let _ = SINK.set(Mutex::new(Sink { file, stderr: foreground }));
}

fn write(level: &str, msg: &str) {
    let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let line = format!("{secs} {level} drover: {msg}\n");
    match SINK.get() {
        Some(sink) => {
            let mut s = sink.lock().unwrap();
            if let Some(f) = s.file.as_mut() {
                let _ = f.write_all(line.as_bytes());
            }
            if s.stderr {
                eprint!("{line}");
            }
        }
        None => eprint!("{line}"),
    }
}

pub fn info(msg: &str) {
    write("INFO", msg);
}

pub fn warn(msg: &str) {
    write("WARNING", msg);
}
