//! Phase 02 gate spike: PTY (portable-pty) + emulation (alacritty_terminal).
//!
//!   pane_spike capture <out.raw> <cols> <rows> <secs> <cmd> [args..]   record raw PTY output
//!   pane_spike render  <in.raw> <cols> <rows>                         print the screen text
//!   pane_spike idle    <panes> <cols> <rows> <secs>                    RSS with N idle shell panes
//!   pane_spike flood   <in.raw> <cols> <rows> <repeat>                 emulation throughput

use std::io::{Read, Write};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use alacritty_terminal::event::VoidListener;
use alacritty_terminal::grid::Dimensions;
use alacritty_terminal::index::{Column, Line};
use alacritty_terminal::term::cell::Flags;
use alacritty_terminal::term::{Config, Term};
use alacritty_terminal::vte::ansi::Processor;
use portable_pty::{CommandBuilder, PtySize, native_pty_system};

struct Size(usize, usize);

impl Dimensions for Size {
    fn total_lines(&self) -> usize {
        self.1
    }
    fn screen_lines(&self) -> usize {
        self.1
    }
    fn columns(&self) -> usize {
        self.0
    }
}

fn new_term(cols: usize, rows: usize) -> Term<VoidListener> {
    let config = Config { scrolling_history: 5000, ..Config::default() };
    Term::new(config, &Size(cols, rows), VoidListener)
}

/// Visible lines, right-trimmed, wide-char spacer cells skipped (same shape as PaneScreen.visible_lines).
fn visible_lines(term: &Term<VoidListener>) -> Vec<String> {
    let grid = term.grid();
    (0..grid.screen_lines() as i32)
        .map(|y| {
            let row = &grid[Line(y)];
            let mut s = String::new();
            for x in 0..grid.columns() {
                let cell = &row[Column(x)];
                if cell.flags.contains(Flags::WIDE_CHAR_SPACER) {
                    continue;
                }
                s.push(cell.c);
                if let Some(extra) = cell.zerowidth() {
                    s.extend(extra);
                }
            }
            s.trim_end().to_string()
        })
        .collect()
}

fn rss_kb() -> u64 {
    std::fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|s| s.lines().find(|l| l.starts_with("VmRSS:")).map(str::to_owned))
        .and_then(|l| l.split_whitespace().nth(1).and_then(|v| v.parse().ok()))
        .unwrap_or(0)
}

fn spawn(cols: u16, rows: u16, argv: &[String]) -> (Box<dyn Read + Send>, Box<dyn portable_pty::Child + Send>, Box<dyn portable_pty::MasterPty + Send>) {
    let pty = native_pty_system()
        .openpty(PtySize { rows, cols, pixel_width: 0, pixel_height: 0 })
        .expect("openpty");
    let mut cmd = CommandBuilder::new(&argv[0]);
    cmd.args(&argv[1..]);
    cmd.env("TERM", "xterm-256color");
    let child = pty.slave.spawn_command(cmd).expect("spawn");
    let reader = pty.master.try_clone_reader().expect("reader");
    (reader, child, pty.master)
}

fn arg<T: std::str::FromStr>(args: &[String], i: usize) -> T {
    args.get(i).and_then(|v| v.parse().ok()).unwrap_or_else(|| panic!("bad or missing arg {i}"))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("capture") => capture(&args),
        Some("render") => render(&args),
        Some("idle") => idle(&args),
        Some("flood") => flood(&args),
        _ => eprintln!("usage: see file header"),
    }
}

fn capture(args: &[String]) {
    let (out, cols, rows, secs): (String, u16, u16, u64) = (arg(args, 2), arg(args, 3), arg(args, 4), arg(args, 5));
    let (mut reader, mut child, _master) = spawn(cols, rows, &args[6..]);
    let buf = Arc::new(Mutex::new(Vec::new()));
    let sink = buf.clone();
    std::thread::spawn(move || {
        let mut chunk = [0u8; 8192];
        while let Ok(n) = reader.read(&mut chunk) {
            if n == 0 {
                break;
            }
            sink.lock().unwrap().extend_from_slice(&chunk[..n]);
        }
    });
    std::thread::sleep(Duration::from_secs(secs));
    let _ = child.kill();
    let data = buf.lock().unwrap().clone();
    std::fs::File::create(&out).and_then(|mut f| f.write_all(&data)).expect("write raw");
    eprintln!("captured {} bytes", data.len());
}

fn render(args: &[String]) {
    let (path, cols, rows): (String, usize, usize) = (arg(args, 2), arg(args, 3), arg(args, 4));
    let data = std::fs::read(path).expect("read raw");
    let mut term = new_term(cols, rows);
    let mut parser: Processor = Processor::new();
    parser.advance(&mut term, &data);
    println!("{}", visible_lines(&term).join("\n"));
}

fn idle(args: &[String]) {
    let (n, cols, rows, secs): (usize, u16, u16, u64) = (arg(args, 2), arg(args, 3), arg(args, 4), arg(args, 5));
    let before = rss_kb();
    let mut keep = Vec::new();
    for _ in 0..n {
        let (mut reader, child, master) = spawn(cols, rows, &["sh".to_string()]);
        let term = Arc::new(Mutex::new(new_term(cols as usize, rows as usize)));
        let t = term.clone();
        std::thread::spawn(move || {
            let mut parser: Processor = Processor::new();
            let mut chunk = [0u8; 8192];
            while let Ok(k) = reader.read(&mut chunk) {
                if k == 0 {
                    break;
                }
                parser.advance(&mut *t.lock().unwrap(), &chunk[..k]);
            }
        });
        keep.push((term, child, master));
    }
    std::thread::sleep(Duration::from_secs(secs));
    let after = rss_kb();
    println!("panes={n} rss_before={before}KB rss_after={after}KB per_pane={}KB", (after - before) / n.max(1) as u64);
    for (_, mut child, _) in keep {
        let _ = child.kill();
    }
}

fn flood(args: &[String]) {
    let (path, cols, rows, repeat): (String, usize, usize, usize) = (arg(args, 2), arg(args, 3), arg(args, 4), arg(args, 5));
    let data = std::fs::read(path).expect("read raw");
    let mut term = new_term(cols, rows);
    let mut parser: Processor = Processor::new();
    let start = Instant::now();
    for _ in 0..repeat {
        parser.advance(&mut term, &data);
    }
    let secs = start.elapsed().as_secs_f64();
    let mb = (data.len() * repeat) as f64 / 1_048_576.0;
    println!("fed {mb:.1} MB in {secs:.2}s = {:.0} MB/s, rss={}KB", mb / secs, rss_kb());
}
