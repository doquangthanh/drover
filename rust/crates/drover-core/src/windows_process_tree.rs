//! Windows agent detection: there is no foreground process group, so look at what the pane's shell started.
//! A Toolhelp snapshot gives the process tree; each descendant's command line (NtQueryInformationProcess) goes
//! through the same `agent_kind_from_argv` as on Linux. Nearest descendant first: `claude.cmd` -> cmd -> node cli.js.

use crate::foreground_probe::agent_kind_from_argv;
use std::ffi::c_void;

type Handle = *mut c_void;
const INVALID_HANDLE: Handle = -1isize as Handle;
const TH32CS_SNAPPROCESS: u32 = 0x2;
const PROCESS_QUERY_LIMITED_INFORMATION: u32 = 0x1000;
const PROCESS_COMMAND_LINE_INFORMATION: u32 = 60; // Windows 8.1+
const MAX_PATH: usize = 260;

#[repr(C)]
struct ProcessEntry32W {
    size: u32,
    usage: u32,
    pid: u32,
    default_heap_id: usize,
    module_id: u32,
    threads: u32,
    parent_pid: u32,
    pri_class_base: i32,
    flags: u32,
    exe_file: [u16; MAX_PATH],
}

#[repr(C)]
struct UnicodeString {
    length: u16, // bytes
    maximum_length: u16,
    buffer: *const u16,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn CreateToolhelp32Snapshot(flags: u32, pid: u32) -> Handle;
    fn Process32FirstW(snapshot: Handle, entry: *mut ProcessEntry32W) -> i32;
    fn Process32NextW(snapshot: Handle, entry: *mut ProcessEntry32W) -> i32;
    fn OpenProcess(access: u32, inherit: i32, pid: u32) -> Handle;
    fn CloseHandle(handle: Handle) -> i32;
    fn LocalFree(mem: *mut c_void) -> *mut c_void;
}

#[link(name = "ntdll")]
unsafe extern "system" {
    fn NtQueryInformationProcess(process: Handle, class: u32, info: *mut c_void, len: u32, ret_len: *mut u32) -> i32;
}

#[link(name = "shell32")]
unsafe extern "system" {
    fn CommandLineToArgvW(cmd_line: *const u16, argc: *mut i32) -> *mut *mut u16;
}

struct Proc {
    pid: u32,
    parent: u32,
    exe: String,
}

/// Every running process with its parent; empty if the snapshot fails.
fn snapshot() -> Vec<Proc> {
    let mut out = Vec::new();
    // SAFETY: plain Win32 calls; `entry.size` is set as the API requires and the handle is closed below.
    unsafe {
        let snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if snap == INVALID_HANDLE || snap.is_null() {
            return out;
        }
        let mut entry: ProcessEntry32W = std::mem::zeroed();
        entry.size = size_of::<ProcessEntry32W>() as u32;
        let mut more = Process32FirstW(snap, &mut entry) != 0;
        while more {
            let len = entry.exe_file.iter().position(|c| *c == 0).unwrap_or(MAX_PATH);
            out.push(Proc { pid: entry.pid, parent: entry.parent_pid, exe: String::from_utf16_lossy(&entry.exe_file[..len]) });
            more = Process32NextW(snap, &mut entry) != 0;
        }
        CloseHandle(snap);
    }
    out
}

/// Command line of a process as argv; None when it cannot be read (gone, or another user's).
fn process_argv(pid: u32) -> Option<Vec<String>> {
    // SAFETY: the buffer is sized from the first call and 8-byte aligned (u64) for the UNICODE_STRING header;
    // CommandLineToArgvW's result is freed with LocalFree as documented; the process handle is always closed.
    unsafe {
        let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if process.is_null() {
            return None;
        }
        let mut needed = 0u32;
        NtQueryInformationProcess(process, PROCESS_COMMAND_LINE_INFORMATION, std::ptr::null_mut(), 0, &mut needed);
        let mut buf = vec![0u64; (needed as usize).div_ceil(8).max(2)];
        let status = NtQueryInformationProcess(
            process, PROCESS_COMMAND_LINE_INFORMATION, buf.as_mut_ptr().cast(), (buf.len() * 8) as u32, &mut needed);
        CloseHandle(process);
        if status < 0 {
            return None;
        }
        let us = &*(buf.as_ptr() as *const UnicodeString);
        if us.buffer.is_null() || us.length == 0 {
            return None;
        }
        let mut wide = std::slice::from_raw_parts(us.buffer, us.length as usize / 2).to_vec();
        wide.push(0);
        let mut argc = 0i32;
        let argv = CommandLineToArgvW(wide.as_ptr(), &mut argc);
        if argv.is_null() {
            return None;
        }
        let args = (0..argc.max(0) as usize)
            .map(|i| {
                let p = *argv.add(i);
                let len = (0..).take_while(|&j| *p.add(j) != 0).count();
                String::from_utf16_lossy(std::slice::from_raw_parts(p, len))
            })
            .collect();
        LocalFree(argv.cast());
        Some(args)
    }
}

/// Agent started (directly or not) by the shell `shell_pid`: its pid and rule-set id, nearest descendant first.
pub fn descendant_agent(shell_pid: u32, kinds: &[&str]) -> Option<(u32, String)> {
    let procs = snapshot();
    let mut level = vec![shell_pid];
    let mut seen = vec![shell_pid];
    while !level.is_empty() {
        let children: Vec<&Proc> =
            procs.iter().filter(|p| level.contains(&p.parent) && !seen.contains(&p.pid) && p.pid != 0).collect();
        for child in &children {
            let argv = process_argv(child.pid).unwrap_or_else(|| vec![child.exe.clone()]);
            if let Some(kind) = agent_kind_from_argv(&argv, kinds) {
                return Some((child.pid, kind));
            }
        }
        level = children.iter().map(|p| p.pid).collect();
        seen.extend(&level);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn own_command_line_and_parent_are_readable() {
        let me = std::process::id();
        let argv = process_argv(me).expect("own command line");
        assert!(argv[0].to_lowercase().contains("drover_core"), "{argv:?}");
        assert!(snapshot().iter().any(|p| p.pid == me && p.parent != 0));
    }

    #[test]
    fn finds_an_agent_started_by_a_shell() {
        // cmd -> ping (a long-lived child); "ping" stands in for an agent's rule-set id.
        let mut shell = std::process::Command::new("cmd").args(["/c", "ping -n 30 127.0.0.1 >NUL"]).spawn().unwrap();
        let found = (0..50).find_map(|_| {
            std::thread::sleep(std::time::Duration::from_millis(100));
            descendant_agent(shell.id(), &["ping", "shell"])
        });
        let _ = shell.kill();
        assert_eq!(found.map(|(_, kind)| kind).as_deref(), Some("ping"));
        assert_eq!(descendant_agent(std::process::id(), &["claude"]), None);
    }
}
