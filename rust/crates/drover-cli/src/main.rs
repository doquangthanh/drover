//! `dr`: the Drover CLI front door. Agent commands that run on every turn (`ls`, `read`, `send`, `wait`, `prompt`,
//! `keys`, ...) are answered here over /rpc in a few ms; everything else, and anything this parser is not sure
//! about, runs in the Python CLI (`dr-py`) unchanged. With the `server` feature it also hosts the Rust daemon.

mod ctrl_c_handling;
mod daemon_rpc;
mod drover_paths;
mod fast_args;
mod fast_commands;
mod fast_ls_command;
mod fast_run_command;
mod hook_claude;
mod python_command_line;
mod python_fallback;
mod python_json;
mod python_output;

use std::ffi::OsString;

use fast_commands::Outcome;

fn main() {
    ctrl_c_handling::exit_130();
    let raw: Vec<OsString> = std::env::args_os().skip(1).collect();
    std::process::exit(dispatch(&raw));
}

fn dispatch(raw: &[OsString]) -> i32 {
    // Non-UTF-8 arguments: Python decodes them its own way.
    let Some(args) = raw.iter().map(|a| a.to_str().map(str::to_string)).collect::<Option<Vec<String>>>() else {
        return python_fallback::run(raw, None);
    };
    #[cfg(feature = "server")]
    if let [cmd, sub, rest @ ..] = args.as_slice()
        && cmd == "server"
        && sub == "run"
    {
        return server_run(rest);
    }
    match fast_args::parse_fast(&args).map(fast_commands::run) {
        Some(Outcome::Exit(code)) => code,
        Some(Outcome::Delegate) | None => python_fallback::run(raw, python_output::consumed_stdin()),
        Some(Outcome::DelegateWith(args)) => {
            python_fallback::run(&args.into_iter().map(OsString::from).collect::<Vec<_>>(), None)
        }
    }
}

#[cfg(feature = "server")]
fn server_run(rest: &[String]) -> i32 {
    let mut listen = "127.0.0.1".to_string();
    let mut background = false;
    let mut it = rest.iter();
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--background" => background = true,
            "--listen" => listen = it.next().cloned().unwrap_or_default(),
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
