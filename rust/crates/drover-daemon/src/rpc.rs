//! JSON-RPC errors, parameter helpers and the method table type. Port of `rpc/rpc_registry.py`.

use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;

use serde_json::{Value, json};

use crate::ctx::Ctx;

// Error codes surfaced to the CLI as exit codes where it makes sense.
pub const E_GENERAL: i64 = 1;
pub const E_TIMEOUT: i64 = 2;
pub const E_NOT_FOUND: i64 = 3;
pub const E_POLICY: i64 = 4;
pub const E_BAD_PARAMS: i64 = 5;
pub const E_BLOCKED: i64 = 6;
pub const E_STALLED: i64 = 7;
pub const E_NO_METHOD: i64 = -32601;

#[derive(Debug, Clone)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
    pub data: Option<Value>,
}

impl RpcError {
    pub fn new(code: i64, message: impl Into<String>) -> Self {
        Self { code, message: message.into(), data: None }
    }

    pub fn to_json(&self) -> Value {
        let mut out = json!({"code": self.code, "message": self.message});
        if let Some(d) = &self.data {
            out["data"] = d.clone();
        }
        out
    }
}

pub type RpcResult = Result<Value, RpcError>;

/// `not found: <what>` like Python's KeyError mapping in the registry.
pub fn not_found(what: impl std::fmt::Display) -> RpcError {
    RpcError::new(E_NOT_FOUND, format!("not found: {what}"))
}

pub fn bad(message: impl Into<String>) -> RpcError {
    RpcError::new(E_BAD_PARAMS, message)
}

/// Required non-empty string parameter.
pub fn need_str(p: &Value, key: &str) -> Result<String, RpcError> {
    match p.get(key) {
        None | Some(Value::Null) => Err(bad(format!("missing parameter: {key}"))),
        Some(Value::String(s)) if s.is_empty() => Err(bad(format!("missing parameter: {key}"))),
        Some(Value::String(s)) => Ok(s.clone()),
        Some(_) => Err(bad(format!("{key} must be str"))),
    }
}

/// Optional parameter as text: missing/null -> "", numbers and bools as Python's str() would print them.
pub fn opt_str(p: &Value, key: &str) -> String {
    match p.get(key) {
        None | Some(Value::Null) => String::new(),
        Some(Value::String(s)) => s.clone(),
        Some(Value::Bool(b)) => if *b { "True" } else { "False" }.into(),
        Some(v) => v.to_string(),
    }
}

/// Python truthiness of a parameter.
pub fn truthy(p: &Value, key: &str) -> bool {
    match p.get(key) {
        None | Some(Value::Null) => false,
        Some(Value::Bool(b)) => *b,
        Some(Value::Number(n)) => n.as_f64().is_some_and(|f| f != 0.0),
        Some(Value::String(s)) => !s.is_empty(),
        Some(Value::Array(a)) => !a.is_empty(),
        Some(Value::Object(o)) => !o.is_empty(),
    }
}

/// `p.get(key, default)` then truthiness (for flags whose default is true).
pub fn flag(p: &Value, key: &str, default: bool) -> bool {
    if p.get(key).is_none() { default } else { truthy(p, key) }
}

pub fn opt_f64(p: &Value, key: &str, default: f64) -> Result<f64, RpcError> {
    match p.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(Value::Number(n)) => Ok(n.as_f64().unwrap_or(default)),
        Some(Value::String(s)) => s.trim().parse().map_err(|_| bad(format!("could not convert string to float: '{s}'"))),
        Some(_) => Err(bad(format!("{key} must be a number"))),
    }
}

pub fn opt_i64(p: &Value, key: &str, default: i64) -> Result<i64, RpcError> {
    match p.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(Value::Number(n)) => Ok(n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)).unwrap_or(default)),
        Some(Value::String(s)) => {
            s.trim().parse().map_err(|_| bad(format!("invalid literal for int() with base 10: '{s}'")))
        }
        Some(_) => Err(bad(format!("{key} must be a number"))),
    }
}

pub type BoxFuture = Pin<Box<dyn Future<Output = RpcResult> + Send>>;
pub type Handler = fn(Arc<Ctx>, Value) -> BoxFuture;

pub struct MethodSpec {
    pub name: &'static str,
    pub doc: &'static str,
    pub params: &'static str,
    pub handler: Handler,
}

/// Declare an RPC method: `method!("pane.list", "doc", "params", handler_fn)`; the handler is
/// `async fn(Arc<Ctx>, Value) -> RpcResult`.
#[macro_export]
macro_rules! method {
    ($name:expr, $doc:expr, $params:expr, $f:path) => {
        $crate::rpc::MethodSpec { name: $name, doc: $doc, params: $params, handler: |c, p| Box::pin($f(c, p)) }
    };
}
