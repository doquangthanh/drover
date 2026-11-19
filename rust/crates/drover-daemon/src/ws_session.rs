//! One websocket client (the drover UI, a phone browser, `dr tui`) talking to this daemon. Port of
//! `ws_client_session.py`; same message shapes:
//!   client -> daemon: {"t":"rpc","id":1,"method":..,"params":..} | {"t":"in","pane":"%3","data":".."}
//!                     | {"t":"attach","pane":"%3"} | {"t":"detach","pane":"%3"}
//!   daemon -> client: {"t":"res","id":1,"result"|"error":..} | {"t":"ev","name":..,"data":..}
//!                     | {"t":"out","pane":"%3","data":".."} | {"t":"replay","pane":"%3","data":".."}

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use axum::extract::ws::{Message, WebSocket};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};

use crate::ctx::Ctx;
use crate::event_hub::{BoundedQueue, Outgoing};

static CLIENT_IDS: AtomicU64 = AtomicU64::new(1);

struct Session {
    ctx: Arc<Ctx>,
    client: crate::remote::link::ClientHandle,
    out: Arc<BoundedQueue>,
    /// pane id -> output listener id
    attached: Mutex<HashMap<String, u64>>,
}

pub async fn run(ctx: Arc<Ctx>, socket: WebSocket, label: String) {
    let id = CLIENT_IDS.fetch_add(1, Ordering::Relaxed);
    ctx.clients.lock().unwrap().insert(id, json!({"id": id, "label": label}));
    let out = Arc::new(BoundedQueue::new(2000));
    let client = crate::remote::link::ClientHandle { id, out: out.clone() };
    let session = Arc::new(Session { ctx: ctx.clone(), client, out: out.clone(), attached: Mutex::new(HashMap::new()) });
    let q = out.clone();
    let sub = ctx.hub.subscribe(move |name, data| {
        q.put(if name == "state" { Outgoing::State } else { Outgoing::Message(json!({"t": "ev", "name": name, "data": data})) });
    });
    out.put(Outgoing::State);
    let (mut sink, mut stream) = socket.split();
    let sender_ctx = ctx.clone();
    let sender = tokio::spawn(async move {
        loop {
            let text = match out.get().await {
                Outgoing::Reply(v) | Outgoing::Message(v) => v.to_string(),
                Outgoing::State => json!({"t": "ev", "name": "state", "data": sender_ctx.combined_state()}).to_string(),
                Outgoing::Resync => json!({"t": "ev", "name": "resync", "data": sender_ctx.combined_state()}).to_string(),
            };
            if sink.send(Message::Text(text.into())).await.is_err() {
                break;
            }
        }
    });
    while let Some(Ok(msg)) = stream.next().await {
        match msg {
            Message::Text(text) => match serde_json::from_str::<Value>(&text) {
                Ok(v) => session.handle(v),
                Err(_) => break,
            },
            Message::Close(_) => break,
            _ => {}
        }
    }
    ctx.hub.unsubscribe(sub);
    let panes: Vec<String> = session.attached.lock().unwrap().keys().cloned().collect();
    for pane_id in panes {
        session.detach(&pane_id);
    }
    ctx.remotes.drop_client(id);
    sender.abort();
    ctx.clients.lock().unwrap().shift_remove(&id);
}

impl Session {
    fn handle(self: &Arc<Self>, msg: Value) {
        if self.ctx.remotes.route_client(&self.client, &msg) {
            return; // a remote machine's pane, tab or space
        }
        let pane_id = match msg.get("pane") {
            Some(Value::String(s)) => s.clone(),
            Some(Value::Null) | None => String::new(),
            Some(v) => v.to_string(),
        };
        match msg.get("t").and_then(Value::as_str) {
            Some("in") => {
                let pane = self.ctx.manager.lock().unwrap().panes.get(&pane_id).cloned();
                if let Some(p) = pane {
                    let data = msg.get("data").and_then(Value::as_str).unwrap_or("");
                    p.state.lock().unwrap().draft.feed(data, drover_core::status_tracker::now_secs());
                    p.write(data);
                }
            }
            Some("attach") => self.attach(&pane_id),
            Some("detach") => self.detach(&pane_id),
            Some("rpc") => {
                let me = self.clone();
                tokio::spawn(async move {
                    let method = msg.get("method").and_then(Value::as_str).unwrap_or("None").to_string();
                    let params = msg.get("params").cloned().filter(|p| !p.is_null()).unwrap_or(json!({}));
                    let id = msg.get("id").cloned().unwrap_or(Value::Null);
                    let reply = match crate::methods::call(me.ctx.clone(), &method, params).await {
                        Ok(result) => json!({"t": "res", "id": id, "result": result}),
                        Err(e) => json!({"t": "res", "id": id, "error": e.to_json()}),
                    };
                    me.out.put(Outgoing::Reply(reply));
                });
            }
            _ => {}
        }
    }

    fn attach(&self, pane_id: &str) {
        let Some(pane) = self.ctx.manager.lock().unwrap().panes.get(pane_id).cloned() else { return };
        // Always replay (also on re-attach after a resync/reconnect) so the viewer is never blank.
        let mut attached = self.attached.lock().unwrap();
        if let Some(old) = attached.remove(pane_id) {
            pane.remove_output_listener(old);
        }
        let q = self.out.clone();
        let listener = pane.attach(
            |replay| self.out.put(Outgoing::Message(json!({"t": "replay", "pane": pane_id, "data": replay}))),
            move |id, data| q.put(Outgoing::Message(json!({"t": "out", "pane": id, "data": data}))),
        );
        attached.insert(pane_id.to_string(), listener);
    }

    fn detach(&self, pane_id: &str) {
        let Some(listener) = self.attached.lock().unwrap().remove(pane_id) else { return };
        if let Some(pane) = self.ctx.manager.lock().unwrap().panes.get(pane_id) {
            pane.remove_output_listener(listener);
        }
    }
}
