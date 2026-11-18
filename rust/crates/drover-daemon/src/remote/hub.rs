//! Links to all remote machines, kept in step with machines.toml, and routing of client traffic to the right one.
//! Port of `remote_hub.py` plus the routing in `ws_client_session.py` / `web_server._call_remote`.

use std::sync::{Arc, Mutex};
use std::time::{Duration, SystemTime};

use indexmap::IndexMap;
use serde_json::{Value, json};

use super::ids::{foreign_ids, prefix_ids, strip_ids};
use super::link::{ClientHandle, Emit, RemoteLink};
use super::registry::{load_machines, machines_file};
use crate::event_hub::EventHub;
use crate::rpc::{E_BAD_PARAMS, RpcError};
use crate::settings::Settings;

pub struct RemoteHub {
    links: Mutex<IndexMap<String, Arc<RemoteLink>>>,
    mtime: Mutex<Option<Option<SystemTime>>>,
    emit: Emit,
}

impl RemoteHub {
    pub fn new(hub: Arc<EventHub>, settings: Arc<Mutex<Settings>>) -> Self {
        let emit: Emit = Arc::new(move |name, data| {
            if name == "state" || name == "machines" {
                hub.emit("state", Value::Null);
                return;
            }
            if name == "status" {
                let pane = &data["pane"];
                let name = pane["name"].as_str().unwrap_or("agent");
                crate::notify::notify_state(&settings.lock().unwrap(), name, pane["kind"].as_str().unwrap_or_default(),
                                            data["new"].as_str().unwrap_or_default(), pane["title"].as_str().unwrap_or_default());
            }
            hub.emit(name, data);
        });
        Self { links: Default::default(), mtime: Mutex::new(None), emit }
    }

    /// Start/stop links to match machines.toml (called on start, by housekeeping and after edits).
    pub fn sync_from_file(&self) {
        let mtime = std::fs::metadata(machines_file()).and_then(|m| m.modified()).ok();
        {
            let mut seen = self.mtime.lock().unwrap();
            if *seen == Some(mtime) {
                return;
            }
            *seen = Some(mtime);
        }
        let wanted = load_machines();
        let mut links = self.links.lock().unwrap();
        links.retain(|alias, link| {
            let keep = wanted.get(alias) == Some(&link.machine);
            if !keep {
                link.stop();
            }
            keep
        });
        for (alias, machine) in wanted {
            if !links.contains_key(&alias) {
                let link = RemoteLink::new(machine, self.emit.clone());
                link.start();
                links.insert(alias, link);
            }
        }
        drop(links);
        (self.emit)("state", Value::Null);
    }

    /// Force a re-read even when the file time did not change (machine.add / machine.remove).
    pub fn resync(&self) {
        *self.mtime.lock().unwrap() = None;
        self.sync_from_file();
    }

    pub fn link(&self, alias: &str) -> Option<Arc<RemoteLink>> {
        self.links.lock().unwrap().get(alias).cloned()
    }

    /// The machine alias when `value` ("vps", "vps:%3") belongs to a linked machine.
    pub fn owner(&self, value: &str) -> Option<String> {
        let alias = value.split(':').next().filter(|a| !a.is_empty())?;
        let owned = self.links.lock().unwrap().contains_key(alias) && (value == alias || value.starts_with(&format!("{alias}:")));
        owned.then(|| alias.to_string())
    }

    pub fn public_state(&self) -> Value {
        json!(self.links.lock().unwrap().values().map(|l| l.public()).collect::<Vec<_>>())
    }

    pub fn drop_client(&self, client_id: u64) {
        for link in self.links.lock().unwrap().values() {
            link.drop_client(client_id);
        }
    }

    pub fn stop_all(&self) {
        for link in self.links.lock().unwrap().values() {
            link.stop();
        }
    }

    /// Route a websocket message from a local client; true when a remote machine took it (or refused it).
    pub fn route_client(&self, client: &ClientHandle, msg: &Value) -> bool {
        let kind = msg["t"].as_str().unwrap_or_default();
        let pane = msg["pane"].as_str().unwrap_or_default();
        let routed = if pane.is_empty() { super::ids::route_of(&msg["params"]) } else { pane.to_string() };
        let Some(alias) = self.owner(&routed) else { return false };
        let Some(link) = self.link(&alias) else { return false };
        if kind == "rpc" {
            let mixed = foreign_ids(&msg["params"], &alias);
            if !mixed.is_empty() {
                let error = json!({"code": E_BAD_PARAMS, "message": format!("ids from different machines in one call ({})", mixed.join(", "))});
                client.out.put(crate::event_hub::Outgoing::Reply(json!({"t": "res", "id": msg["id"], "error": error})));
                return true;
            }
            link.forward(client, msg);
        } else {
            let mut msg = msg.clone();
            msg["pane"] = json!(routed);
            link.forward(client, &msg);
        }
        true
    }

    /// `/rpc` call for a remote machine (CLI, scripts). None when no linked machine owns the call.
    pub async fn call_remote(&self, method: &str, params: &Value) -> Option<Result<Value, RpcError>> {
        let alias = self.owner(&super::ids::route_of(params))?;
        let link = self.link(&alias)?;
        let mixed = foreign_ids(params, &alias);
        if !mixed.is_empty() {
            return Some(Err(RpcError::new(E_BAD_PARAMS, format!("ids from different machines in one call ({}); use ids on {alias}", mixed.join(", ")))));
        }
        let timeout = params["timeout"].as_f64().unwrap_or(25.0) + 5.0;
        let mut remote = strip_ids(params, &alias);
        if let Some(caller) = params["caller"].as_str().filter(|c| !c.is_empty()) {
            remote["caller"] = json!(format!("hub:{caller}")); // keep the policy in force remotely
        }
        Some(link.call(method, remote, Duration::from_secs_f64(timeout.max(1.0))).await
            .map(|r| prefix_ids(&r, &alias)).map_err(|e| RpcError::new(1, e)))
    }
}
