//! One RPC to the running daemon, the way `daemon_client.call` does it: read daemon.json, POST /rpc over
//! HTTP/1.0 on 127.0.0.1 with the bearer token, read until the daemon closes.
//!
//! No autostart here: when the daemon can't be reached the caller hands the command to the Python CLI, which
//! starts it (`ensure_daemon`), so that logic lives in one place.

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::time::Duration;

use serde_json::{Map, Value};

use crate::python_json;

#[derive(Debug)]
pub enum RpcError {
    /// Nothing was sent: no usable daemon.json or nothing listening. Safe to hand the command to Python.
    Unavailable,
    /// The request went out but no valid reply came back. Not retried (the daemon may have acted on it);
    /// reported like Python's `DaemonUnavailable` (exit 10).
    Lost(String),
    /// The daemon answered `{"error": {"code", "message"}}`.
    Failed { code: i64, message: String },
}

fn daemon_address() -> Result<(u16, String), RpcError> {
    let text = std::fs::read_to_string(crate::drover_paths::state_dir().join("daemon.json"))
        .map_err(|_| RpcError::Unavailable)?;
    let info: Value = serde_json::from_str(&text).map_err(|_| RpcError::Unavailable)?;
    match (info["port"].as_u64().and_then(|p| u16::try_from(p).ok()), info["token"].as_str()) {
        (Some(port), Some(token)) if port > 0 => Ok((port, token.to_string())),
        _ => Err(RpcError::Unavailable),
    }
}

/// `call(method, params, timeout)`: adds `caller` = `$DR_PANE_ID` like the Python client; returns `result`.
pub fn call(method: &str, mut params: Map<String, Value>, timeout: Duration) -> Result<Value, RpcError> {
    if let Ok(caller) = std::env::var("DR_PANE_ID")
        && !caller.is_empty()
        && !params.contains_key("caller")
    {
        params.insert("caller".into(), Value::String(caller));
    }
    let mut payload = Map::new();
    payload.insert("method".into(), Value::String(method.into()));
    payload.insert("params".into(), Value::Object(params));
    let body = python_json::dumps(&Value::Object(payload));

    let (port, token) = daemon_address()?;
    let reply = post(port, &token, &body, timeout)?;
    let Value::Object(mut reply) = reply else {
        return Err(RpcError::Lost("unexpected reply from drover daemon".into()));
    };
    if let Some(error) = reply.get("error") {
        let code = error.get("code").map(python_int).unwrap_or(Some(1)).unwrap_or(1);
        let message = error.get("message").map(python_json::py_str).unwrap_or_else(|| "error".into());
        return Err(RpcError::Failed { code, message });
    }
    Ok(reply.remove("result").unwrap_or(Value::Null))
}

/// `int(v)` for an error code: 5, 5.0 and "5" all give 5.
fn python_int(v: &Value) -> Option<i64> {
    match v {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().filter(|f| f.is_finite()).map(|f| f.trunc() as i64)),
        Value::String(s) => s.trim().parse().ok(),
        Value::Bool(b) => Some(*b as i64),
        _ => None,
    }
}

fn post(port: u16, token: &str, body: &str, timeout: Duration) -> Result<Value, RpcError> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut sock = TcpStream::connect_timeout(&addr, timeout.min(Duration::from_secs(5))).map_err(|_| RpcError::Unavailable)?;
    exchange(&mut sock, port, token, body, timeout).map_err(|e| RpcError::Lost(format!("cannot reach drover daemon: {e}")))
}

fn exchange(sock: &mut TcpStream, port: u16, token: &str, body: &str, timeout: Duration) -> std::io::Result<Value> {
    sock.set_read_timeout(Some(timeout))?;
    sock.set_write_timeout(Some(timeout))?;
    let _ = sock.set_nodelay(true);
    let request = format!(
        "POST /rpc HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\nContent-Length: {}\r\nContent-Type: application/json\r\n\
         Authorization: Bearer {token}\r\n\r\n{body}",
        body.len()
    );
    sock.write_all(request.as_bytes())?;
    let mut raw = Vec::new();
    sock.read_to_end(&mut raw)?;
    let split = raw.windows(4).position(|w| w == b"\r\n\r\n").ok_or_else(|| bad("bad response from daemon"))?;
    serde_json::from_slice(&raw[split + 4..]).map_err(|e| bad(&e.to_string()))
}

fn bad(msg: &str) -> std::io::Error {
    std::io::Error::new(std::io::ErrorKind::InvalidData, msg.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn error_codes_convert_like_python_int() {
        assert_eq!(python_int(&json!(5)), Some(5));
        assert_eq!(python_int(&json!(5.9)), Some(5));
        assert_eq!(python_int(&json!(" 7 ")), Some(7));
        assert_eq!(python_int(&json!("x")), None);
    }

    #[test]
    fn nothing_listening_is_unavailable_not_lost() {
        // nothing sent yet: the command may safely go to Python
        assert!(matches!(post(1, "t", "{}", Duration::from_millis(500)), Err(RpcError::Unavailable)));
    }
}
