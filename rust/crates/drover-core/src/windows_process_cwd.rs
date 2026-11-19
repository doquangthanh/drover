//! Windows: the current folder of another process (Linux reads `/proc/<pid>/cwd`). It lives in the process's
//! PEB -> RTL_USER_PROCESS_PARAMETERS.CurrentDirectory; read with ReadProcessMemory. 64-bit layouts only; any
//! failure (gone, other user, 32-bit process) is None. cmd and agents keep it current; PowerShell's `cd` does
//! not change it, so a PowerShell pane follows its agent, else stays at its start folder.

use std::ffi::c_void;

use crate::windows_process_tree::{
    CloseHandle, Handle, NtQueryInformationProcess, OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, UnicodeString,
};

const PROCESS_VM_READ: u32 = 0x0010;
const PROCESS_BASIC_INFORMATION: u32 = 0;
const PEB_PROCESS_PARAMETERS: usize = 0x20; // x64 PEB.ProcessParameters
const PARAMS_CURRENT_DIRECTORY: usize = 0x38; // x64 RTL_USER_PROCESS_PARAMETERS.CurrentDirectory.DosPath
const MAX_PATH_BYTES: u16 = 32_767 * 2;

#[repr(C)]
struct BasicInformation {
    exit_status: isize,
    peb: usize,
    affinity_mask: usize,
    base_priority: isize,
    pid: usize,
    parent_pid: usize,
}

#[link(name = "kernel32")]
unsafe extern "system" {
    fn ReadProcessMemory(process: Handle, address: *const c_void, buf: *mut c_void, size: usize, read: *mut usize) -> i32;
}

/// Copy a `T` out of the other process at `address`.
unsafe fn read<T>(process: Handle, address: usize) -> Option<T> {
    let mut value = std::mem::MaybeUninit::<T>::uninit();
    let mut got = 0usize;
    // SAFETY (caller): `process` has PROCESS_VM_READ; we only accept a full read of size_of::<T>() bytes.
    let ok = unsafe {
        ReadProcessMemory(process, address as *const c_void, value.as_mut_ptr().cast(), size_of::<T>(), &mut got)
    };
    (ok != 0 && got == size_of::<T>()).then(|| unsafe { value.assume_init() })
}

#[cfg(target_pointer_width = "64")]
pub fn process_cwd(pid: u32) -> Option<String> {
    // SAFETY: plain Win32 calls on a handle we own and close; every remote read is size-checked and the path
    // length is capped before the buffer is allocated.
    unsafe {
        let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, 0, pid);
        if process.is_null() {
            return None;
        }
        let cwd = (|| {
            let mut info: BasicInformation = std::mem::zeroed();
            let status = NtQueryInformationProcess(process, PROCESS_BASIC_INFORMATION, (&mut info as *mut BasicInformation).cast(),
                                                   size_of::<BasicInformation>() as u32, std::ptr::null_mut());
            if status < 0 || info.peb == 0 {
                return None;
            }
            let params: usize = read(process, info.peb + PEB_PROCESS_PARAMETERS)?;
            let dir: UnicodeString = read(process, params + PARAMS_CURRENT_DIRECTORY)?;
            if dir.buffer.is_null() || dir.length == 0 || dir.length > MAX_PATH_BYTES {
                return None;
            }
            let mut wide = vec![0u16; dir.length as usize / 2];
            let mut got = 0usize;
            let ok = ReadProcessMemory(process, dir.buffer.cast(), wide.as_mut_ptr().cast(), dir.length as usize, &mut got);
            (ok != 0 && got == dir.length as usize).then(|| String::from_utf16_lossy(&wide))
        })();
        CloseHandle(process);
        cwd.map(|c| trim_separator(&c))
    }
}

#[cfg(not(target_pointer_width = "64"))]
pub fn process_cwd(_pid: u32) -> Option<String> {
    None
}

/// `C:\work\` -> `C:\work`, but `C:\` stays.
fn trim_separator(path: &str) -> String {
    if path.len() > 3 { path.trim_end_matches('\\').to_string() } else { path.to_string() }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_a_child_processes_folder() {
        let dir = std::env::temp_dir();
        let mut child = std::process::Command::new("cmd").args(["/c", "ping -n 30 127.0.0.1 >NUL"]).current_dir(&dir)
            .spawn().unwrap();
        std::thread::sleep(std::time::Duration::from_millis(300));
        let got = process_cwd(child.id());
        let _ = child.kill();
        let want = trim_separator(&dir.to_string_lossy());
        assert_eq!(got.map(|g| g.to_lowercase()), Some(want.to_lowercase()));
        assert_eq!(trim_separator(r"C:\"), r"C:\");
    }
}
