//! Fan-out of daemon events to connected clients, and the per-client outbound queue. Port of `event_hub.py`.
//!
//! Listeners run on the emitting thread (often with the manager locked), so they must only queue work.
//! A "state" event carries no data here: each client builds the snapshot when it sends it, outside every lock.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use serde_json::Value;
use tokio::sync::Notify;

type Listener = Arc<dyn Fn(&str, &Value) + Send + Sync>;

#[derive(Default)]
pub struct EventHub {
    listeners: Mutex<Vec<(u64, Listener)>>,
    next: AtomicU64,
}

impl EventHub {
    pub fn subscribe(&self, listener: impl Fn(&str, &Value) + Send + Sync + 'static) -> u64 {
        let id = self.next.fetch_add(1, Ordering::Relaxed);
        self.listeners.lock().unwrap().push((id, Arc::new(listener)));
        id
    }

    pub fn unsubscribe(&self, id: u64) {
        self.listeners.lock().unwrap().retain(|(i, _)| *i != id);
    }

    pub fn emit(&self, name: &str, data: Value) {
        let listeners: Vec<Listener> = self.listeners.lock().unwrap().iter().map(|(_, l)| l.clone()).collect();
        for l in listeners {
            l(name, &data);
        }
    }
}

/// One item waiting to go out to a websocket client.
pub enum Outgoing {
    /// RPC reply: never dropped.
    Reply(Value),
    /// Droppable message (event, terminal output, replay).
    Message(Value),
    /// Send the current combined state as `{"t":"ev","name":"state"}`.
    State,
    /// Client fell behind: send `{"t":"ev","name":"resync"}` with fresh state.
    Resync,
}

/// Per-client outbound queue. When a slow client falls behind, droppable traffic is discarded and the client is
/// told to resync (re-fetch state and re-attach panes, which replays their output).
pub struct BoundedQueue {
    items: Mutex<(VecDeque<Outgoing>, bool)>,
    ready: Notify,
    max: usize,
}

impl BoundedQueue {
    pub fn new(max: usize) -> Self {
        Self { items: Mutex::new((VecDeque::new(), false)), ready: Notify::new(), max }
    }

    pub fn put(&self, item: Outgoing) {
        let mut guard = self.items.lock().unwrap();
        let (items, overflowed) = &mut *guard;
        let important = matches!(item, Outgoing::Reply(_));
        if *overflowed && !important {
            return;
        }
        if !important && items.len() >= self.max {
            *overflowed = true;
            items.retain(|i| matches!(i, Outgoing::Reply(_)));
            items.push_back(Outgoing::Resync);
        } else {
            items.push_back(item);
        }
        drop(guard);
        self.ready.notify_one();
    }

    pub async fn get(&self) -> Outgoing {
        loop {
            {
                let mut guard = self.items.lock().unwrap();
                if let Some(item) = guard.0.pop_front() {
                    if matches!(item, Outgoing::Resync) {
                        guard.1 = false;
                    }
                    return item;
                }
            }
            self.ready.notified().await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[tokio::test]
    async fn overflow_drops_output_keeps_replies_and_asks_for_resync() {
        let q = BoundedQueue::new(3);
        q.put(Outgoing::Message(json!(1)));
        q.put(Outgoing::Reply(json!("r1")));
        q.put(Outgoing::Message(json!(2)));
        q.put(Outgoing::Message(json!(3))); // full: drop messages, keep the reply, add resync
        q.put(Outgoing::Message(json!(4))); // ignored until the resync went out
        q.put(Outgoing::Reply(json!("r2")));
        assert!(matches!(q.get().await, Outgoing::Reply(v) if v == "r1"));
        assert!(matches!(q.get().await, Outgoing::Resync));
        assert!(matches!(q.get().await, Outgoing::Reply(v) if v == "r2"));
        q.put(Outgoing::Message(json!(5)));
        assert!(matches!(q.get().await, Outgoing::Message(v) if v == 5));
    }
}
