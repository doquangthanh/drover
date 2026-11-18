//! Remote machines: this daemon (the hub) links to drover daemons on other machines over the system `ssh` and shows
//! their spaces and panes with prefixed ids ("vps:%3"). Port of `src/drover/remote/*`.

pub mod hub;
pub mod ids;
pub mod link;
pub mod registry;
pub mod ssh;
