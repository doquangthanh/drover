//! A reconnecting /ws client of the daemon, on its own thread. The UI sends `Command`s and drains `Incoming`s;
//! `wake` is called whenever something arrives so the UI can repaint without polling hard.
//!
//! After a daemon restart (self-update) the port and token can change: every reconnect re-reads daemon.json and
//! re-attaches the panes that were attached, so the viewer is never blank.

use std::collections::{HashMap, HashSet};
use std::io::ErrorKind;
use std::net::TcpStream;
use std::path::PathBuf;
use std::sync::mpsc::{Receiver, Sender, channel};
use std::time::Duration;

use serde_json::{Value, json};
use tungstenite::stream::MaybeTlsStream;
use tungstenite::{Message, WebSocket};

use crate::wire::ServerMsg;

pub type RpcReply = Sender<Result<Value, String>>;

pub enum Command {
    Rpc { method: String, params: Value, reply: Option<RpcReply> },
    Attach(String),
    Detach(String),
    Input { pane: String, data: String },
}

#[derive(Debug, Clone, PartialEq)]
pub enum Incoming {
    Connected,
    Disconnected(String),
    Event { name: String, data: Value },
    Output { pane: String, data: String, replay: bool },
}

pub struct Client {
    pub commands: Sender<Command>,
    pub incoming: Receiver<Incoming>,
}

/// The daemon's state folder, as the daemon computes it (`DROVER_STATE_DIR`, else the platform state dir).
pub fn state_dir() -> PathBuf {
    if let Some(dir) = std::env::var_os("DROVER_STATE_DIR") {
        return PathBuf::from(dir);
    }
    if cfg!(windows)
        && let Some(local) = std::env::var_os("LOCALAPPDATA")
    {
        return PathBuf::from(local).join("drover");
    }
    dirs::state_dir().or_else(dirs::data_local_dir).unwrap_or_else(|| PathBuf::from(".")).join("drover")
}

pub fn daemon_address() -> Result<(u64, String), String> {
    let text = std::fs::read_to_string(state_dir().join("daemon.json")).map_err(|e| format!("daemon.json: {e}"))?;
    let v: Value = serde_json::from_str(&text).map_err(|e| format!("daemon.json: {e}"))?;
    match (v["port"].as_u64(), v["token"].as_str()) {
        (Some(port), Some(token)) if port > 0 => Ok((port, token.to_string())),
        _ => Err("daemon.json has no port/token".into()),
    }
}

type Socket = WebSocket<MaybeTlsStream<TcpStream>>;

fn connect() -> Result<Socket, String> {
    let (port, token) = daemon_address()?;
    let (ws, _) = tungstenite::connect(format!("ws://127.0.0.1:{port}/ws?token={token}")).map_err(|e| e.to_string())?;
    if let MaybeTlsStream::Plain(tcp) = ws.get_ref() {
        // Short reads let one thread both read and send.
        tcp.set_read_timeout(Some(Duration::from_millis(15))).map_err(|e| e.to_string())?;
        let _ = tcp.set_nodelay(true);
    }
    Ok(ws)
}

struct Session {
    attached: HashSet<String>,
    pending: HashMap<u64, RpcReply>,
    next_id: u64,
}

impl Session {
    fn send_command(&mut self, ws: &mut Socket, cmd: Command) -> tungstenite::Result<()> {
        let msg = match cmd {
            Command::Rpc { method, params, reply } => {
                self.next_id += 1;
                if let Some(r) = reply {
                    self.pending.insert(self.next_id, r);
                }
                json!({"t": "rpc", "id": self.next_id, "method": method, "params": params})
            }
            Command::Attach(pane) => {
                self.attached.insert(pane.clone());
                json!({"t": "attach", "pane": pane})
            }
            Command::Detach(pane) => {
                self.attached.remove(&pane);
                json!({"t": "detach", "pane": pane})
            }
            Command::Input { pane, data } => json!({"t": "in", "pane": pane, "data": data}),
        };
        ws.send(Message::Text(msg.to_string().into()))
    }
}

/// Start the client thread. `wake` runs on that thread after each batch of incoming messages.
pub fn start(wake: impl Fn() + Send + 'static) -> Client {
    let (cmd_tx, cmd_rx) = channel::<Command>();
    let (in_tx, in_rx) = channel::<Incoming>();
    std::thread::Builder::new()
        .name("drover-client".into())
        .spawn(move || run(cmd_rx, in_tx, wake))
        .expect("spawn client thread");
    Client { commands: cmd_tx, incoming: in_rx }
}

fn run(commands: Receiver<Command>, incoming: Sender<Incoming>, wake: impl Fn()) {
    let mut session = Session { attached: HashSet::new(), pending: HashMap::new(), next_id: 0 };
    let mut backoff = Duration::from_millis(250);
    loop {
        let mut ws = match connect() {
            Ok(ws) => ws,
            Err(e) => {
                if incoming.send(Incoming::Disconnected(e)).is_err() {
                    return; // the UI is gone
                }
                wake();
                std::thread::sleep(backoff);
                backoff = (backoff * 2).min(Duration::from_secs(5));
                continue;
            }
        };
        backoff = Duration::from_millis(250);
        let _ = incoming.send(Incoming::Connected);
        for pane in session.attached.clone() {
            let _ = ws.send(Message::Text(json!({"t": "attach", "pane": pane}).to_string().into()));
        }
        wake();
        let reason = serve(&mut ws, &mut session, &commands, &incoming, &wake);
        // Calls in flight will never get their reply on this socket.
        for (_, reply) in session.pending.drain() {
            let _ = reply.send(Err("connection to the daemon lost".into()));
        }
        match reason {
            None => return,
            Some(why) => {
                let _ = incoming.send(Incoming::Disconnected(why));
                wake();
            }
        }
    }
}

/// Pump one connection. Some(reason) = reconnect; None = the UI dropped its handles, stop.
fn serve(ws: &mut Socket, session: &mut Session, commands: &Receiver<Command>, incoming: &Sender<Incoming>,
         wake: &impl Fn()) -> Option<String> {
    loop {
        loop {
            match commands.try_recv() {
                Ok(cmd) => {
                    if let Err(e) = session.send_command(ws, cmd) {
                        return Some(e.to_string());
                    }
                }
                Err(std::sync::mpsc::TryRecvError::Empty) => break,
                Err(std::sync::mpsc::TryRecvError::Disconnected) => return None,
            }
        }
        let mut got = false;
        loop {
            match ws.read() {
                Ok(Message::Text(text)) => {
                    got = true;
                    let item = match ServerMsg::parse(&text) {
                        ServerMsg::Reply { id, result } => {
                            if let Some(reply) = session.pending.remove(&id) {
                                let _ = reply.send(result);
                            }
                            continue;
                        }
                        ServerMsg::Event { name, data } => Incoming::Event { name, data },
                        ServerMsg::Output { pane, data, replay } => Incoming::Output { pane, data, replay },
                        ServerMsg::Other => continue,
                    };
                    if incoming.send(item).is_err() {
                        return None;
                    }
                }
                Ok(Message::Close(_)) => return Some("daemon closed the connection".into()),
                Ok(_) => {}
                Err(tungstenite::Error::Io(e)) if matches!(e.kind(), ErrorKind::WouldBlock | ErrorKind::TimedOut) => break,
                Err(e) => return Some(e.to_string()),
            }
        }
        if got {
            wake();
        }
    }
}
