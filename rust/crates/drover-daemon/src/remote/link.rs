//! Websocket session from this (hub) daemon to one remote drover daemon, carried by `ssh -W`. Port of
//! `remote_link.py`: reconnects with backoff, re-attaches watched panes, prefixes everything coming back.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use tokio::sync::{mpsc, oneshot};
use tokio_tungstenite::tungstenite::Message;

use drover_core::status_tracker::now_secs;

use super::ids::{prefix_ids, strip_ids, tag_machine};
use super::registry::Machine;
use crate::event_hub::{BoundedQueue, Outgoing};

/// A local websocket client (UI) the link answers or streams output to.
#[derive(Clone)]
pub struct ClientHandle {
    pub id: u64,
    pub out: Arc<BoundedQueue>,
}

enum Waiter {
    Client(ClientHandle, Value),
    Call(oneshot::Sender<Value>),
}

pub type Emit = Arc<dyn Fn(&str, Value) + Send + Sync>;

#[derive(Default)]
struct LinkState {
    status: String,
    error: String,
    latency_ms: Option<u64>,
    info: Value,
    snapshot: Value,
    attempt: u32,
    retry_at: f64,
}

pub struct RemoteLink {
    pub machine: Machine,
    emit: Emit,
    st: Mutex<LinkState>,
    ws: Mutex<Option<mpsc::UnboundedSender<String>>>,
    ids: AtomicU64,
    pending: Mutex<HashMap<u64, Waiter>>,
    /// remote pane id -> local clients watching it
    viewers: Mutex<HashMap<String, Vec<ClientHandle>>>,
    task: Mutex<Option<tokio::task::JoinHandle<()>>>,
}

impl RemoteLink {
    pub fn new(machine: Machine, emit: Emit) -> Arc<Self> {
        let st = LinkState { status: "connecting".into(), ..Default::default() };
        Arc::new(Self { machine, emit, st: Mutex::new(st), ws: Mutex::new(None), ids: AtomicU64::new(1),
                        pending: Default::default(), viewers: Default::default(), task: Mutex::new(None) })
    }

    fn alias(&self) -> &str {
        &self.machine.alias
    }

    pub fn start(self: &Arc<Self>) {
        let me = self.clone();
        *self.task.lock().unwrap() = Some(tokio::spawn(async move { me.run_forever().await }));
    }

    /// Stops the loop; dropping its future kills the ssh process.
    pub fn stop(&self) {
        if let Some(t) = self.task.lock().unwrap().take() {
            t.abort();
        }
        self.ws.lock().unwrap().take();
        self.fail_pending("link stopped");
    }

    fn set_status(&self, status: &str, error: &str) {
        let mut st = self.st.lock().unwrap();
        st.status = status.into();
        st.error = error.into();
    }

    async fn run_forever(self: Arc<Self>) {
        loop {
            if let Err(e) = self.clone().connect_once().await {
                crate::log::info(&format!("remote {}: {e}", self.alias()));
                self.set_status("error", &e);
            }
            let delay = {
                let mut st = self.st.lock().unwrap();
                st.attempt += 1;
                let delay = 60u64.min(1 << st.attempt.min(6));
                st.retry_at = now_secs() + delay as f64;
                delay
            };
            (self.emit)("state", Value::Null);
            tokio::time::sleep(Duration::from_secs(delay)).await;
        }
    }

    async fn connect_once(self: Arc<Self>) -> Result<(), String> {
        self.set_status("connecting", "");
        (self.emit)("state", Value::Null);
        let info = super::ssh::ensure_remote_daemon(&self.machine).await?;
        let mut tunnel = super::ssh::open_tunnel(&self.machine, info["port"].as_u64().unwrap_or(0))?;
        let stream = tokio::io::join(tunnel.stdout.take().unwrap(), tunnel.stdin.take().unwrap());
        let url = format!("ws://127.0.0.1:{}/ws?token={}&label=hub", info["port"], info["token"].as_str().unwrap_or_default());
        let (ws, _) = tokio_tungstenite::client_async(url, stream).await.map_err(|e| format!("websocket: {e}"))?;
        let (mut sink, mut source) = ws.split();
        let (tx, mut rx) = mpsc::unbounded_channel::<String>();
        let writer = tokio::spawn(async move {
            while let Some(text) = rx.recv().await {
                if sink.send(Message::Text(text.into())).await.is_err() {
                    break;
                }
            }
        });
        for pane in self.viewers.lock().unwrap().keys() {
            let _ = tx.send(json!({"t": "attach", "pane": pane}).to_string());
        }
        *self.ws.lock().unwrap() = Some(tx);
        {
            let mut st = self.st.lock().unwrap();
            st.attempt = 0;
            st.status = "connected".into();
            st.error.clear();
            st.info = info;
        }
        (self.emit)("state", Value::Null);
        let pinger = tokio::spawn(self.clone().ping_loop());
        while let Some(Ok(msg)) = source.next().await {
            if let Message::Text(text) = msg
                && let Ok(v) = serde_json::from_str::<Value>(&text)
            {
                self.on_message(v);
            }
        }
        pinger.abort();
        writer.abort();
        self.ws.lock().unwrap().take();
        self.fail_pending(&format!("connection to {} lost", self.alias()));
        drop(tunnel);
        Err("connection closed".into())
    }

    /// Answer every in-flight request so no client or `call()` waits forever.
    fn fail_pending(&self, message: &str) {
        let pending: Vec<Waiter> = self.pending.lock().unwrap().drain().map(|(_, w)| w).collect();
        for waiter in pending {
            match waiter {
                Waiter::Call(tx) => { let _ = tx.send(json!({"error": {"code": 1, "message": message}})); }
                Waiter::Client(c, id) => c.out.put(Outgoing::Reply(json!({"t": "res", "id": id, "error": {"code": 1, "message": message}}))),
            }
        }
    }

    async fn ping_loop(self: Arc<Self>) {
        loop {
            let started = Instant::now();
            if let Ok(info) = self.call("server.info", json!({}), Duration::from_secs(30)).await {
                let mut st = self.st.lock().unwrap();
                if let (Some(dst), Some(src)) = (st.info.as_object_mut(), info.as_object()) {
                    dst.extend(src.clone());
                }
                st.latency_ms = Some(started.elapsed().as_millis() as u64);
                drop(st);
                (self.emit)("machines", Value::Null);
            }
            tokio::time::sleep(Duration::from_secs(15)).await;
        }
    }

    fn on_message(&self, msg: Value) {
        let alias = self.alias().to_string();
        match msg["t"].as_str() {
            Some("ev") => {
                let (name, data) = (msg["name"].as_str().unwrap_or_default(), &msg["data"]);
                match name {
                    "state" | "resync" => {
                        self.st.lock().unwrap().snapshot = tag_machine(prefix_ids(data, &alias), &alias);
                        (self.emit)("state", Value::Null);
                    }
                    "pane" => {
                        let mut data = prefix_ids(data, &alias);
                        data["machine"] = json!(alias);
                        (self.emit)("pane", data);
                    }
                    "status" | "policy" => (self.emit)(name, prefix_ids(data, &alias)),
                    _ => {}
                }
            }
            Some("out" | "replay") => {
                let pane = msg["pane"].as_str().unwrap_or_default().to_string();
                let mut relay = msg.clone();
                relay["pane"] = json!(format!("{alias}:{pane}"));
                for c in self.viewers.lock().unwrap().get(&pane).into_iter().flatten() {
                    c.out.put(Outgoing::Message(relay.clone()));
                }
            }
            Some("res") => {
                let waiter = msg["id"].as_u64().and_then(|id| self.pending.lock().unwrap().remove(&id));
                match waiter {
                    Some(Waiter::Call(tx)) => { let _ = tx.send(msg); }
                    Some(Waiter::Client(c, client_id)) => {
                        let mut reply = msg;
                        reply["id"] = client_id;
                        if reply.get("result").is_some() {
                            reply["result"] = prefix_ids(&reply["result"], &alias);
                        }
                        c.out.put(Outgoing::Reply(reply));
                    }
                    None => {}
                }
            }
            _ => {}
        }
    }

    fn send(&self, msg: &Value) -> bool {
        self.ws.lock().unwrap().as_ref().is_some_and(|tx| tx.send(msg.to_string()).is_ok())
    }

    /// RPC on the remote daemon (ids as the remote knows them). Err carries the remote's message.
    pub async fn call(&self, method: &str, params: Value, timeout: Duration) -> Result<Value, String> {
        let id = self.ids.fetch_add(1, Ordering::Relaxed);
        let (tx, rx) = oneshot::channel();
        self.pending.lock().unwrap().insert(id, Waiter::Call(tx));
        if !self.send(&json!({"t": "rpc", "id": id, "method": method, "params": params})) {
            self.pending.lock().unwrap().remove(&id);
            return Err(format!("{} is not connected", self.alias()));
        }
        let reply = tokio::time::timeout(timeout, rx).await;
        self.pending.lock().unwrap().remove(&id);
        let reply = reply.map_err(|_| format!("{} did not answer in time", self.alias()))?.map_err(|_| "link stopped".to_string())?;
        match reply.get("error") {
            Some(e) => Err(e["message"].as_str().unwrap_or("remote error").to_string()),
            None => Ok(reply["result"].clone()),
        }
    }

    /// A message from a local client for this machine (ids still prefixed).
    pub fn forward(&self, client: &ClientHandle, msg: &Value) {
        let mut msg = strip_ids(msg, self.alias());
        let (kind, pane) = (msg["t"].as_str().unwrap_or_default().to_string(), msg["pane"].as_str().unwrap_or_default().to_string());
        // Track viewers even while disconnected so a reconnect re-attaches (and replays) for them.
        if kind == "attach" {
            let mut viewers = self.viewers.lock().unwrap();
            let list = viewers.entry(pane.clone()).or_default();
            if !list.iter().any(|c| c.id == client.id) {
                list.push(client.clone());
            }
        } else if kind == "detach" {
            let mut viewers = self.viewers.lock().unwrap();
            if let Some(list) = viewers.get_mut(&pane) {
                list.retain(|c| c.id != client.id);
                if !list.is_empty() {
                    return; // others still watching: keep the remote stream alive
                }
            }
            viewers.remove(&pane);
        }
        if kind == "rpc" {
            let (id, client_id) = (self.ids.fetch_add(1, Ordering::Relaxed), msg["id"].clone());
            self.pending.lock().unwrap().insert(id, Waiter::Client(client.clone(), client_id.clone()));
            msg["id"] = json!(id);
            if !self.send(&msg) {
                self.pending.lock().unwrap().remove(&id);
                let error = json!({"code": 1, "message": format!("{} is not connected", self.alias())});
                client.out.put(Outgoing::Reply(json!({"t": "res", "id": client_id, "error": error})));
            }
            return;
        }
        self.send(&msg);
    }

    pub fn drop_client(&self, client_id: u64) {
        for list in self.viewers.lock().unwrap().values_mut() {
            list.retain(|c| c.id != client_id);
        }
    }

    pub fn public(&self) -> Value {
        let st = self.st.lock().unwrap();
        let info = json!({"version": st.info["version"], "platform": st.info["platform"], "uptime": st.info["uptime"]});
        json!({"alias": self.alias(), "target": self.machine.target, "status": st.status, "error": st.error,
               "latency_ms": st.latency_ms, "retry_at": st.retry_at, "attempt": st.attempt, "info": info,
               "snapshot": if st.status == "connected" { st.snapshot.clone() } else { json!({}) }})
    }
}

