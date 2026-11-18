//! One running `claude` process in stream-json mode, spoken to the way claude_agent_sdk does it:
//! - stdin: user messages and control requests/responses, one JSON object per line;
//! - stdout: conversation messages, control responses to our requests, and control requests from the CLI
//!   (`can_use_tool` permission questions, `control_cancel_request` when it gives up on one).
//! The process is killed when this object is dropped.

use std::collections::{HashMap, VecDeque};
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, oneshot};

/// What the CLI sends besides answers to our own control requests.
pub enum Incoming {
    Message(Value),
    /// `can_use_tool`: answer with `respond(request_id, ...)`.
    Permission { request_id: String, request: Value },
    /// The CLI no longer waits for this permission answer.
    Cancel(String),
}

pub struct CliOptions {
    pub exe: PathBuf,
    pub cwd: String,
    pub permission_mode: String,
    pub model: Option<String>,
    pub resume: Option<String>,
}

type Pending = Arc<Mutex<HashMap<String, oneshot::Sender<Result<Value, String>>>>>;

pub struct ClaudeCli {
    stdin: mpsc::UnboundedSender<String>,
    pending: Pending,
    pub incoming: tokio::sync::Mutex<mpsc::UnboundedReceiver<Incoming>>,
    stderr_tail: Arc<Mutex<VecDeque<String>>>,
    counter: AtomicU64,
    _child: Child,
    /// The `initialize` answer: slash commands, models, output style.
    pub info: Value,
}

/// Same flags claude_agent_sdk passes for drover's chat (no system prompt override beyond the SDK's empty one,
/// partial messages on, permission questions over stdio).
fn args(o: &CliOptions) -> Vec<String> {
    let mut a: Vec<String> = ["--output-format", "stream-json", "--verbose", "--system-prompt", ""].map(String::from).into();
    if let Some(model) = &o.model {
        a.extend(["--model".into(), model.clone()]);
    }
    a.extend(["--permission-prompt-tool".into(), "stdio".into(), "--permission-mode".into(), o.permission_mode.clone()]);
    if let Some(id) = &o.resume {
        a.push(format!("--resume={id}"));
    }
    a.extend(["--include-partial-messages", "--input-format", "stream-json"].map(String::from));
    a
}

impl ClaudeCli {
    pub async fn spawn(o: &CliOptions) -> Result<Arc<Self>, String> {
        let mut cmd = Command::new(&o.exe);
        cmd.args(args(o)).current_dir(&o.cwd).env("PWD", &o.cwd).env("CLAUDE_CODE_ENTRYPOINT", "sdk-py")
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).kill_on_drop(true);
        for (key, _) in std::env::vars().filter(|(k, _)| crate::launch::is_session_var(k) && k != "CLAUDE_CODE_ENTRYPOINT") {
            cmd.env_remove(key);
        }
        #[cfg(windows)]
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: the daemon has no console to share
        let mut child = cmd.spawn().map_err(|e| format!("cannot start {}: {e}", o.exe.display()))?;
        let (mut stdin, stdout, stderr) = (child.stdin.take().unwrap(), child.stdout.take().unwrap(), child.stderr.take().unwrap());

        let (stdin_tx, mut stdin_rx) = mpsc::unbounded_channel::<String>();
        tokio::spawn(async move {
            while let Some(line) = stdin_rx.recv().await {
                if stdin.write_all(line.as_bytes()).await.is_err() || stdin.flush().await.is_err() {
                    break;
                }
            }
        });
        let stderr_tail: Arc<Mutex<VecDeque<String>>> = Default::default();
        let tail = stderr_tail.clone();
        tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                let mut t = tail.lock().unwrap();
                t.push_back(line);
                if t.len() > 20 {
                    t.pop_front();
                }
            }
        });
        let pending: Pending = Default::default();
        let (in_tx, in_rx) = mpsc::unbounded_channel();
        tokio::spawn(read_stdout(stdout, pending.clone(), in_tx));

        let mut cli = Self { stdin: stdin_tx, pending, incoming: tokio::sync::Mutex::new(in_rx), stderr_tail,
                             counter: AtomicU64::new(0), _child: child, info: Value::Null };
        // MCP servers may take a while to start, hence the long wait.
        cli.info = cli.control(json!({"subtype": "initialize", "hooks": null}), Duration::from_secs(60)).await
            .map_err(|e| format!("{e}{}", cli.stderr_hint()))?;
        Ok(Arc::new(cli))
    }

    fn send(&self, msg: Value) -> Result<(), String> {
        self.stdin.send(format!("{msg}\n")).map_err(|_| format!("the agent process has exited{}", self.stderr_hint()))
    }

    /// Last lines the CLI printed on stderr, for error messages.
    pub fn stderr_hint(&self) -> String {
        let tail = self.stderr_tail.lock().unwrap();
        if tail.is_empty() { String::new() } else { format!(" ({})", tail.iter().rev().take(3).rev().cloned().collect::<Vec<_>>().join(" | ")) }
    }

    pub fn send_user(&self, content: Value) -> Result<(), String> {
        self.send(json!({"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": null, "session_id": "default"}))
    }

    /// Send a control request and wait for its answer (`response.response`).
    pub async fn control(&self, request: Value, timeout: Duration) -> Result<Value, String> {
        let n = self.counter.fetch_add(1, Ordering::Relaxed) + 1;
        let id = format!("req_{n}_{}", &super::new_id()[..8]);
        let (tx, rx) = oneshot::channel();
        self.pending.lock().unwrap().insert(id.clone(), tx);
        let subtype = request["subtype"].as_str().unwrap_or_default().to_string();
        self.send(json!({"type": "control_request", "request_id": id, "request": request}))?;
        let answer = tokio::time::timeout(timeout, rx).await;
        self.pending.lock().unwrap().remove(&id);
        match answer {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => Err(format!("the agent process has exited{}", self.stderr_hint())),
            Err(_) => Err(format!("Control request timeout: {subtype}")),
        }
    }

    /// Answer a control request from the CLI (a permission question).
    pub fn respond(&self, request_id: &str, response: Value) -> Result<(), String> {
        self.send(json!({"type": "control_response", "response": {"subtype": "success", "request_id": request_id, "response": response}}))
    }

    /// Refuse a control request we do not handle (hook callbacks, SDK MCP servers: drover registers none).
    pub fn respond_error(&self, request_id: &str, error: &str) -> Result<(), String> {
        self.send(json!({"type": "control_response", "response": {"subtype": "error", "request_id": request_id, "error": error}}))
    }
}

async fn read_stdout(stdout: tokio::process::ChildStdout, pending: Pending, incoming: mpsc::UnboundedSender<Incoming>) {
    let mut lines = BufReader::new(stdout).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        let Ok(msg) = serde_json::from_str::<Value>(&line) else { continue };
        match msg["type"].as_str() {
            Some("control_response") => {
                let r = &msg["response"];
                let waiter = r["request_id"].as_str().and_then(|id| pending.lock().unwrap().remove(id));
                if let Some(tx) = waiter {
                    let _ = tx.send(if r["subtype"] == "error" {
                        Err(r["error"].as_str().unwrap_or("Unknown error").to_string())
                    } else {
                        Ok(if r["response"].is_object() { r["response"].clone() } else { json!({}) })
                    });
                }
            }
            Some("control_request") => {
                let request_id = msg["request_id"].as_str().unwrap_or_default().to_string();
                let _ = incoming.send(Incoming::Permission { request_id, request: msg["request"].clone() });
            }
            Some("control_cancel_request") => {
                let _ = incoming.send(Incoming::Cancel(msg["request_id"].as_str().unwrap_or_default().to_string()));
            }
            Some("transcript_mirror") => {}
            _ => {
                let _ = incoming.send(Incoming::Message(msg));
            }
        }
    }
    pending.lock().unwrap().clear(); // waiters see "the agent process has exited"; dropping `incoming` ends the turn
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn flags_match_what_the_sdk_passed() {
        let o = CliOptions { exe: "claude".into(), cwd: ".".into(), permission_mode: "plan".into(), model: Some("opus".into()), resume: Some("abc".into()) };
        assert_eq!(args(&o).join(" "), "--output-format stream-json --verbose --system-prompt  --model opus --permission-prompt-tool stdio \
                                       --permission-mode plan --resume=abc --include-partial-messages --input-format stream-json");
    }
}
