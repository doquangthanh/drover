//! Windows: one environment variable of another process (Linux reads `/proc/<pid>/environ`). The block lives at
//! RTL_USER_PROCESS_PARAMETERS.Environment (size at .EnvironmentSize, Windows 8+); read with ReadProcessMemory.
//! Used for the `DROVER_AGENT` wrapper hint. 64-bit layouts only; any failure is None.

#[cfg(target_pointer_width = "64")]
use crate::windows_process_cwd::{read, read_wide, with_process_params};

#[cfg(target_pointer_width = "64")]
const PARAMS_ENVIRONMENT: usize = 0x80; // x64 RTL_USER_PROCESS_PARAMETERS.Environment
#[cfg(target_pointer_width = "64")]
const PARAMS_ENVIRONMENT_SIZE: usize = 0x3F0; // x64 RTL_USER_PROCESS_PARAMETERS.EnvironmentSize (bytes)
#[cfg(target_pointer_width = "64")]
const MAX_ENV_BYTES: usize = 1 << 20;

#[cfg(target_pointer_width = "64")]
pub fn process_env_var(pid: u32, name: &str) -> Option<String> {
    let block = with_process_params(pid, |process, params| {
        // SAFETY: size-checked remote reads; the block size is capped before the buffer is allocated.
        let env: usize = unsafe { read(process, params + PARAMS_ENVIRONMENT)? };
        let size: usize = unsafe { read(process, params + PARAMS_ENVIRONMENT_SIZE)? };
        if env == 0 || size == 0 || size > MAX_ENV_BYTES {
            return None;
        }
        read_wide(process, env, size & !1)
    })?;
    env_block_lookup(&String::from_utf16_lossy(&block), name)
}

#[cfg(not(target_pointer_width = "64"))]
pub fn process_env_var(_pid: u32, _name: &str) -> Option<String> {
    None
}

/// `NAME=value\0NAME2=value\0\0` -> value of `name` (names are case-insensitive on Windows).
fn env_block_lookup(block: &str, name: &str) -> Option<String> {
    block.split('\0').take_while(|e| !e.is_empty()).find_map(|entry| {
        let (key, value) = entry.split_once('=')?;
        key.eq_ignore_ascii_case(name).then(|| value.to_string())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_an_environment_block() {
        let block = "=C:=C:\\work\0Path=C:\\bin\0drover_agent=claude\0\0junk=1";
        assert_eq!(env_block_lookup(block, "DROVER_AGENT").as_deref(), Some("claude"));
        assert_eq!(env_block_lookup(block, "PATH").as_deref(), Some("C:\\bin"));
        assert_eq!(env_block_lookup(block, "junk"), None); // after the terminating empty entry
    }

    #[test]
    fn reads_a_child_processes_variable() {
        let mut child = std::process::Command::new("cmd").args(["/c", "ping -n 30 127.0.0.1 >NUL"])
            .env("DROVER_AGENT", "codex").spawn().unwrap();
        std::thread::sleep(std::time::Duration::from_millis(300));
        let got = process_env_var(child.id(), "DROVER_AGENT");
        let _ = child.kill();
        assert_eq!(got.as_deref(), Some("codex"));
    }
}
