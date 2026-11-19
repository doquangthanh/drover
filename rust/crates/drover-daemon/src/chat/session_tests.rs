//! A whole turn against `fake_claude.py`: streaming, a permission question answered "always", session id saved,
//! options and model switch over the control protocol. No real Claude is started.

use std::time::Duration;

use serde_json::{Value, json};

use crate::chat::manager::ChatManager;
use crate::event_hub::EventHub;

async fn wait_for(what: &str, mut ok: impl FnMut() -> bool) {
    for _ in 0..200 {
        if ok() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
    panic!("timed out waiting for {what}");
}

// Unix only: the fake `claude` is a Python script run through its shebang, found via a ':'-separated PATH.
#[cfg(unix)]
#[tokio::test]
async fn turn_with_permission_against_fake_cli() {
    let root = std::env::temp_dir().join(format!("drover-chat-session-{}", crate::chat::new_id()));
    let bin = root.join("bin");
    std::fs::create_dir_all(&bin).unwrap();
    let fake = bin.join("claude");
    std::fs::copy(concat!(env!("CARGO_MANIFEST_DIR"), "/src/chat/fake_claude.py"), &fake).unwrap();
    #[cfg(unix)]
    std::fs::set_permissions(&fake, std::os::unix::fs::PermissionsExt::from_mode(0o755)).unwrap();
    let args_file = root.join("args.json");
    // SAFETY: the only test touching these variables; set before any process starts.
    unsafe {
        std::env::set_var("PATH", format!("{}:{}", bin.display(), std::env::var("PATH").unwrap_or_default()));
        std::env::set_var("FAKE_CLAUDE_ARGS", &args_file);
    }

    let hub = std::sync::Arc::new(EventHub::default());
    let events = std::sync::Arc::new(std::sync::Mutex::new(Vec::<(String, Value)>::new()));
    let sink = events.clone();
    hub.subscribe(move |name, data| sink.lock().unwrap().push((name.to_string(), data.clone())));
    let chats = ChatManager::new(root.join("chats"), hub);
    let chat = chats.create(root.to_str().unwrap(), Some("t"), None, "default", None).unwrap();

    chat.send("hi", &[]).unwrap();
    assert!(chat.send("again", &[]).is_err(), "a second message while working is refused");
    let pending = || chat.items().into_iter().find(|i| i["kind"] == "permission" && i["status"] == "pending");
    wait_for("the permission question", || pending().is_some()).await;
    assert_eq!(chat.state(), "blocked");
    let request = pending().unwrap()["id"].as_str().unwrap().to_string();
    assert!(chat.answer(&request, true, true));
    wait_for("the end of the turn", || chat.state() == "idle").await;

    let items = chat.items();
    let kinds: Vec<&str> = items.iter().map(|i| i["kind"].as_str().unwrap()).collect();
    assert_eq!(kinds, ["user", "text", "permission", "text", "result"]);
    assert_eq!(items[1]["text"], "Hello");
    assert_eq!(items[2]["status"], "allowed");
    let echoed: Value = serde_json::from_str(items[3]["text"].as_str().unwrap()).unwrap();
    assert_eq!(echoed["behavior"], "allow");
    assert_eq!(echoed["updatedInput"], json!({"command": "ls"}));
    assert_eq!(echoed["updatedPermissions"][0]["type"], "addRules");
    assert_eq!(chat.meta.lock().unwrap()["session_id"], "sess-1");
    let argv: Vec<String> = serde_json::from_str(&std::fs::read_to_string(&args_file).unwrap()).unwrap();
    assert!(argv.contains(&"--permission-prompt-tool".to_string()) && argv.contains(&"--include-partial-messages".to_string()));
    assert!(events.lock().unwrap().iter().any(|(n, d)| n == "chat" && d["op"] == "delta" && d["chat"] == "c1"));
    assert!(events.lock().unwrap().iter().any(|(n, d)| n == "chats" && d[0]["state"] == "blocked"));

    let options = chat.options().await.unwrap();
    assert_eq!(options["commands"][0]["name"], "help");
    assert_eq!(options["models"][0], json!({"value": "opus", "label": "Opus", "description": ""}));
    chat.set_model("opus").await.unwrap(); // goes to the live CLI as a control request
    assert_eq!(chat.to_public()["model"], "opus");

    // Saved to disk: a fresh manager restores the chat and its transcript (live items are never written).
    chats.shutdown().await;
    let again = ChatManager::new(root.join("chats"), std::sync::Arc::new(EventHub::default()));
    assert_eq!(again.get("c1").unwrap().items().len(), 5);
    let _ = std::fs::remove_dir_all(root);
}
