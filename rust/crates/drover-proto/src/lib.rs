//! drover-proto: the client side of the drover daemon protocol (/ws + /rpc), shared by native clients
//! (the GPUI desktop app, later the Rust TUI).

pub mod client;
pub mod store;
pub mod wire;

#[cfg(test)]
mod tests;
