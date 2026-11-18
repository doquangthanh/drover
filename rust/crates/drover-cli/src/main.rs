//! `dr`: the Drover CLI. Phase 03 wires `dr server run` and `dr hook claude`; the rest is ported in phase 06.

mod hook_claude;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let words: Vec<&str> = args.iter().map(String::as_str).collect();
    match words.as_slice() {
        ["server", "run", rest @ ..] => std::process::exit(server_run(rest)),
        ["hook", "claude"] => std::process::exit(hook_claude::run()),
        ["--version"] | ["version"] => println!("dr (rust) {}", env!("CARGO_PKG_VERSION")),
        _ => {
            eprintln!("dr (rust) {}: only `dr server run [--listen ADDR] [--background]` exists yet", env!("CARGO_PKG_VERSION"));
            std::process::exit(2);
        }
    }
}

fn server_run(rest: &[&str]) -> i32 {
    let mut listen = "127.0.0.1".to_string();
    let mut background = false;
    let mut it = rest.iter();
    while let Some(arg) = it.next() {
        match *arg {
            "--background" => background = true,
            "--listen" => listen = it.next().map(|s| s.to_string()).unwrap_or_default(),
            other if other.starts_with("--listen=") => listen = other["--listen=".len()..].to_string(),
            other => {
                eprintln!("error: unknown argument {other}");
                return 2;
            }
        }
    }
    if matches!(listen.as_str(), "0.0.0.0" | "::" | "*") {
        eprintln!("error: refusing to listen on every network interface. Give one address you trust, e.g. your Tailscale IP (100.x.y.z).");
        return 5;
    }
    if !matches!(listen.as_str(), "127.0.0.1" | "localhost") && !listen.starts_with("100.") {
        eprintln!("warning: the UI token travels over plain HTTP; use this only on a private network such as Tailscale.");
    }
    match drover_daemon::serve(&listen, 0, !background) {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("error: {e}");
            1
        }
    }
}
