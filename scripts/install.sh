#!/bin/sh
# Install herd from the latest GitHub release (Linux x64/arm64). No root needed.
#   curl -fsSL https://raw.githubusercontent.com/doquangthanh/herd/main/scripts/install.sh | sh
# Env: HERD_VERSION=v0.1.0 (default: latest), HERD_HOME=~/.local/share/herd, HERD_BIN=~/.local/bin
set -eu

REPO="doquangthanh/herd"
HERD_HOME="${HERD_HOME:-$HOME/.local/share/herd}"
HERD_BIN="${HERD_BIN:-$HOME/.local/bin}"

[ "$(uname -s)" = "Linux" ] || { echo "herd: this installer supports Linux only" >&2; exit 1; }
case "$(uname -m)" in
  x86_64 | amd64) arch="x64" ;;
  aarch64 | arm64) arch="arm64" ;;
  *) echo "herd: unsupported CPU $(uname -m)" >&2; exit 1 ;;
esac

asset="herd-linux-$arch.tar.gz"
if [ -n "${HERD_VERSION:-}" ]; then
  url="https://github.com/$REPO/releases/download/$HERD_VERSION/$asset"
else
  url="https://github.com/$REPO/releases/latest/download/$asset"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "herd: downloading $url"
curl -fSL --proto '=https' "$url" -o "$tmp/$asset"

# Unpack next to the old copy, then swap, so a failed download never breaks a working install.
mkdir -p "$tmp/unpack"
tar -xzf "$tmp/$asset" -C "$tmp/unpack"
[ -x "$tmp/unpack/herd/hd" ] || { echo "herd: archive is missing herd/hd" >&2; exit 1; }
# A running daemon outlives its window and keeps serving the old UI: stop it so the next launch uses the new files.
if [ -x "$HERD_HOME/hd" ]; then "$HERD_HOME/hd" server stop >/dev/null 2>&1 || true; fi
rm -rf "$HERD_HOME"
mkdir -p "$(dirname "$HERD_HOME")" "$HERD_BIN"
mv "$tmp/unpack/herd" "$HERD_HOME"

ln -sf "$HERD_HOME/hd" "$HERD_BIN/hd"
ln -sf "$HERD_HOME/herd" "$HERD_BIN/herd"

# App-menu entry so herd shows up in the desktop launcher (icon ships inside the bundle).
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icon="$HERD_HOME/_internal/herd/web/favicon.png"
mkdir -p "$apps"
cat > "$apps/herd.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Herd
Comment=Workspace for running coding agents
Exec=$HERD_HOME/herd
Icon=$icon
Terminal=false
Categories=Development;
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true

echo "herd: installed to $HERD_HOME (hd, herd linked in $HERD_BIN)"
case ":$PATH:" in
  *":$HERD_BIN:"*) ;;
  *) echo "herd: add $HERD_BIN to PATH:  export PATH=\"$HERD_BIN:\$PATH\"" ;;
esac
echo "herd: run 'hd' to start. Without GTK/WebKit it opens the web UI in your browser."
