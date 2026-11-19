//! Ctrl+C like the Python CLI: a fast command stopped by Ctrl+C exits 130 (`KeyboardInterrupt`); while a delegated
//! Python child runs, we ignore it and let the child decide. Windows console handlers run last-registered first,
//! so `ignore_while_child_runs` takes over from `exit_130`. Elsewhere the default SIGINT already gives 130.

#[cfg(windows)]
mod console {
    pub type Handler = unsafe extern "system" fn(u32) -> i32;
    unsafe extern "system" {
        fn SetConsoleCtrlHandler(handler: Option<Handler>, add: i32) -> i32;
    }
    /// Register a handler function. Never the NULL form: that one is inherited by children.
    pub fn add(handler: Handler) {
        // SAFETY: `handler` is a plain static function; kernel32 is always linked on Windows.
        unsafe {
            SetConsoleCtrlHandler(Some(handler), 1);
        }
    }
}

pub fn exit_130() {
    #[cfg(windows)]
    {
        unsafe extern "system" fn handler(_ctrl: u32) -> i32 {
            std::process::exit(130)
        }
        console::add(handler);
    }
}

pub fn ignore_while_child_runs() {
    #[cfg(windows)]
    {
        unsafe extern "system" fn handler(_ctrl: u32) -> i32 {
            1 // handled: keep waiting for the child's exit code
        }
        console::add(handler);
    }
}
