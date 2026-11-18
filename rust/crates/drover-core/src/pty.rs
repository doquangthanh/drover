//! One child process on a pseudo-terminal (Linux openpty, Windows ConPTY via portable-pty).
//! Replaces `drover/pty/*`. Output is decoded UTF-8 text delivered on a reader thread; exit fires once.

use std::io::{Read, Write};
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};

use portable_pty::{ChildKiller, CommandBuilder, MasterPty, PtySize, native_pty_system};

use crate::utf8_stream::Utf8Stream;

pub struct Pty {
    master: Mutex<Box<dyn MasterPty + Send>>,
    writer: Mutex<Box<dyn Write + Send>>,
    killer: Mutex<Box<dyn ChildKiller + Send + Sync>>,
    alive: Arc<AtomicBool>,
    pub pid: Option<u32>,
}

pub struct SpawnSpec<'a> {
    pub argv: &'a [String],
    pub cwd: &'a str,
    /// Full environment of the child (the caller builds it, like the Python daemon did).
    pub env: &'a [(String, String)],
    pub cols: u16,
    pub rows: u16,
}

fn size(cols: u16, rows: u16) -> PtySize {
    PtySize { rows, cols, pixel_width: 0, pixel_height: 0 }
}

impl Pty {
    pub fn spawn(
        spec: SpawnSpec<'_>,
        mut on_output: impl FnMut(String) + Send + 'static,
        on_exit: impl FnOnce(Option<i32>) + Send + 'static,
    ) -> Result<Arc<Pty>, String> {
        let Some((program, args)) = spec.argv.split_first() else { return Err("empty command".into()) };
        let pair = native_pty_system().openpty(size(spec.cols, spec.rows)).map_err(|e| e.to_string())?;
        let mut cmd = CommandBuilder::new(program);
        cmd.args(args);
        cmd.env_clear();
        for (k, v) in spec.env {
            cmd.env(k, v);
        }
        if !spec.cwd.is_empty() {
            cmd.cwd(spec.cwd); // portable-pty defaults to $HOME otherwise
        }
        let mut child = pair.slave.spawn_command(cmd).map_err(|e| format!("cannot start {program}: {e}"))?;
        drop(pair.slave); // the child holds its own copy; keeping ours would hide EOF on exit
        let mut reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
        let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
        let alive = Arc::new(AtomicBool::new(true));
        let pty = Arc::new(Pty {
            pid: child.process_id(),
            killer: Mutex::new(child.clone_killer()),
            master: Mutex::new(pair.master),
            writer: Mutex::new(writer),
            alive: alive.clone(),
        });
        std::thread::Builder::new()
            .name(format!("pty-{}", pty.pid.unwrap_or(0)))
            .spawn(move || {
                let mut decoder = Utf8Stream::default();
                let mut buf = vec![0u8; 65536];
                loop {
                    match reader.read(&mut buf) {
                        Ok(0) | Err(_) => break, // EOF / EIO once the child side closes
                        Ok(n) => {
                            let text = decoder.decode(&buf[..n]);
                            if !text.is_empty() {
                                on_output(text);
                            }
                        }
                    }
                }
                let code = child.wait().ok().map(|s| s.exit_code() as i32);
                alive.store(false, Ordering::SeqCst);
                on_exit(code);
            })
            .map_err(|e| e.to_string())?;
        Ok(pty)
    }

    pub fn write(&self, data: &str) {
        if self.is_alive() {
            let mut w = self.writer.lock().unwrap();
            let _ = w.write_all(data.as_bytes()).and_then(|_| w.flush());
        }
    }

    pub fn resize(&self, cols: u16, rows: u16) {
        if self.is_alive() {
            let _ = self.master.lock().unwrap().resize(size(cols, rows));
        }
    }

    pub fn kill(&self) {
        let _ = self.killer.lock().unwrap().kill();
    }

    pub fn is_alive(&self) -> bool {
        self.alive.load(Ordering::SeqCst)
    }

    /// Foreground process group of the terminal (POSIX only): which program the user is running in a shell.
    #[cfg(unix)]
    pub fn foreground_pgid(&self) -> Option<i32> {
        self.master.lock().unwrap().process_group_leader()
    }

    #[cfg(not(unix))]
    pub fn foreground_pgid(&self) -> Option<i32> {
        None
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::sync::mpsc;
    use std::time::Duration;

    fn env() -> Vec<(String, String)> {
        vec![("PATH".into(), std::env::var("PATH").unwrap_or_default()), ("TERM".into(), "xterm-256color".into())]
    }

    #[test]
    fn runs_command_in_cwd_and_reports_exit_code() {
        let (out_tx, out_rx) = mpsc::channel();
        let (exit_tx, exit_rx) = mpsc::channel();
        let argv = ["sh".to_string(), "-c".into(), "pwd; exit 3".into()];
        let env = env();
        let spec = SpawnSpec { argv: &argv, cwd: "/tmp", env: &env, cols: 80, rows: 24 };
        let pty = Pty::spawn(spec, move |t| out_tx.send(t).unwrap(), move |c| exit_tx.send(c).unwrap()).unwrap();
        assert_eq!(exit_rx.recv_timeout(Duration::from_secs(10)).unwrap(), Some(3));
        let output: String = out_rx.try_iter().collect();
        assert!(output.contains("/tmp"), "{output:?}");
        assert!(!pty.is_alive());
    }

    #[test]
    fn write_reaches_the_program_and_kill_ends_it() {
        let (out_tx, out_rx) = mpsc::channel::<String>();
        let (exit_tx, exit_rx) = mpsc::channel();
        let argv = ["sh".to_string()];
        let env = env();
        let spec = SpawnSpec { argv: &argv, cwd: "", env: &env, cols: 80, rows: 24 };
        let pty = Pty::spawn(spec, move |t| { let _ = out_tx.send(t); }, move |c| exit_tx.send(c).unwrap()).unwrap();
        pty.write("echo mar''ker\r");
        let mut seen = String::new();
        while !seen.contains("marker") {
            seen.push_str(&out_rx.recv_timeout(Duration::from_secs(10)).expect("output"));
        }
        pty.kill();
        exit_rx.recv_timeout(Duration::from_secs(10)).expect("exit after kill");
        assert!(!pty.is_alive());
    }
}
