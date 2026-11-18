#!/bin/sh
# Run cargo inside a memory/CPU-capped scope so a heavy build cannot freeze the machine.
# Usage: scripts/cargo-capped.sh build --release   (runs in rust/)
set -e
cd "$(dirname "$0")/../rust"
CARGO="${CARGO:-$HOME/.cargo/bin/cargo}"
if systemd-run --user --scope -q true 2>/dev/null; then
  exec systemd-run --user --scope -q -p MemoryMax=3G -p MemorySwapMax=0 -p CPUQuota=200% \
    nice -n 19 ionice -c3 "$CARGO" "$@"
fi
echo "warning: systemd-run unavailable, running without a hard memory cap" >&2
exec nice -n 19 ionice -c3 "$CARGO" "$@"
