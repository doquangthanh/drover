//! RPC for remote machines (machines.toml + live links). Port of the methods in `remote_hub.py`.

use std::sync::Arc;
use std::time::Duration;

use serde_json::{Value, json};

use crate::ctx::Ctx;
use crate::method;
use crate::remote::registry::{Machine, load_machines, save_machines, validate_new};
use crate::rpc::{E_NOT_FOUND, MethodSpec, RpcError, RpcResult, bad, need_str, opt_i64, opt_str, truthy};

pub fn methods() -> Vec<MethodSpec> {
    vec![
        method!("machine.list", "Remote machines and their connection state", "", list),
        method!("machine.add", "Add a machine to machines.toml", "alias, target, port?, key?, install?", add),
        method!("machine.remove", "Forget a machine (its agents keep running there)", "alias", remove),
        method!("machine.test", "Try SSH + remote dr without saving", "target, port?, key?", test),
    ]
}

fn machine_from(p: &Value, alias: &str, target: &str) -> Result<Machine, RpcError> {
    let port = match opt_i64(p, "port", 22)? { 0 => 22, n => u16::try_from(n).map_err(|_| bad("port must be 1-65535"))? };
    Ok(Machine { port, key: opt_str(p, "key"), ..Machine::new(alias, target) })
}

/// The newest wheel in the repo's dist/ (dev installs), uploaded by `install`.
fn local_wheel() -> Option<std::path::PathBuf> {
    let dist = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../dist");
    let mut wheels: Vec<_> = std::fs::read_dir(dist).ok()?.flatten().map(|e| e.path())
        .filter(|p| p.file_name().is_some_and(|n| { let n = n.to_string_lossy(); n.starts_with("drover-") && n.ends_with(".whl") }))
        .collect();
    wheels.sort();
    wheels.pop()
}

async fn list(ctx: Arc<Ctx>, _p: Value) -> RpcResult {
    Ok(ctx.remotes.public_state())
}

async fn add(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut machines = load_machines();
    let (alias, target) = (need_str(&p, "alias")?, need_str(&p, "target")?);
    validate_new(&alias, &target, &machines).map_err(bad)?;
    let machine = machine_from(&p, &alias, &target)?;
    if truthy(&p, "install") {
        let label = alias.clone();
        crate::remote::ssh::install_dr(&machine, local_wheel().as_deref(), |step| crate::log::info(&format!("install {label}: {step}")))
            .await.map_err(|e| RpcError::new(1, format!("install on {alias} failed: {e}")))?;
    }
    machines.insert(alias.clone(), machine);
    save_machines(&machines).map_err(|e| RpcError::new(1, e.to_string()))?;
    ctx.remotes.resync();
    Ok(json!({"alias": alias}))
}

async fn remove(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut machines = load_machines();
    if machines.shift_remove(&need_str(&p, "alias")?).is_none() {
        return Err(RpcError::new(E_NOT_FOUND, "no such machine"));
    }
    save_machines(&machines).map_err(|e| RpcError::new(1, e.to_string()))?;
    ctx.remotes.resync();
    Ok(Value::Null)
}

async fn test(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let machine = machine_from(&p, "test", &need_str(&p, "target")?)?;
    let probe = crate::remote::ssh::run(&machine, "true", Duration::from_secs(30)).await;
    match probe {
        Ok(o) if o.code == 0 => {}
        Ok(o) => return Ok(json!({"ok": false, "steps": [], "error": if o.stderr.is_empty() { "ssh failed".into() } else { o.stderr }})),
        Err(e) => return Ok(json!({"ok": false, "steps": [], "error": e})),
    }
    match crate::remote::ssh::ensure_remote_daemon(&machine).await {
        Ok(info) => Ok(json!({"ok": true, "steps": ["ssh ok", format!("dr {} running", info["version"].as_str().unwrap_or_default())]})),
        Err(e) => Ok(json!({"ok": false, "steps": ["ssh ok"], "error": e})),
    }
}
