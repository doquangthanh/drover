//! drover-proto: the client side of the drover daemon protocol (/ws + /rpc), shared by native clients
//! (the GPUI desktop app, later the Rust TUI).

pub mod agent_tree;
pub mod changes;
pub mod files;
pub mod client;
pub mod store;
pub mod wire;

#[cfg(test)]
mod agent_tree_tests;
#[cfg(test)]
mod changes_tests;
#[cfg(test)]
mod tests;
