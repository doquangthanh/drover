#!/bin/sh
# Install drover from the latest GitHub release (Linux x64/arm64). No root needed.
#   curl -fsSL https://raw.githubusercontent.com/doquangthanh/drover/main/scripts/install.sh | sh
# Env: DROVER_VERSION=v0.1.0 (default: latest), DROVER_HOME=~/.local/share/drover, DROVER_BIN=~/.local/bin,
#      DROVER_ARCHIVE=/path/drover-linux-x64.tar.gz (install a local build, no download, no checksum)
set -eu

REPO="doquangthanh/drover"
DROVER_HOME="${DROVER_HOME:-$HOME/.local/share/drover}"
DROVER_BIN="${DROVER_BIN:-$HOME/.local/bin}"

[ "$(uname -s)" = "Linux" ] || { echo "drover: this installer supports Linux only" >&2; exit 1; }
case "$(uname -m)" in
  x86_64 | amd64) arch="x64" ;;
  aarch64 | arm64) arch="arm64" ;;
  *) echo "drover: unsupported CPU $(uname -m)" >&2; exit 1 ;;
esac

asset="drover-linux-$arch.tar.gz"
if [ -n "${DROVER_VERSION:-}" ]; then
  url="https://github.com/$REPO/releases/download/$DROVER_VERSION/$asset"
else
  url="https://github.com/$REPO/releases/latest/download/$asset"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

if [ -n "${DROVER_ARCHIVE:-}" ]; then
  cp "$DROVER_ARCHIVE" "$tmp/$asset"
else
  echo "drover: downloading $url"
  curl -fSL --proto '=https' "$url" -o "$tmp/$asset"
  # Releases from the Rust move on carry a SHA-256; older ones don't, so a missing file only skips the check.
  if curl -fsSL --proto '=https' "$url.sha256" -o "$tmp/sum" 2>/dev/null; then
    want="$(cut -d' ' -f1 "$tmp/sum")"
    got="$(sha256sum "$tmp/$asset" | cut -d' ' -f1)"
    [ "$want" = "$got" ] || { echo "drover: checksum mismatch, not installing" >&2; exit 1; }
    echo "drover: checksum ok"
  fi
fi

# Unpack next to the old copy, then swap, so a failed download never breaks a working install.
mkdir -p "$tmp/unpack"
tar -xzf "$tmp/$asset" -C "$tmp/unpack"
[ -x "$tmp/unpack/drover/dr" ] || { echo "drover: archive is missing drover/dr" >&2; exit 1; }
# A running daemon outlives its window and keeps serving the old UI: stop it so the next launch uses the new files.
if [ -x "$DROVER_HOME/dr" ]; then "$DROVER_HOME/dr" server stop >/dev/null 2>&1 || true; fi
rm -rf "$DROVER_HOME"
mkdir -p "$(dirname "$DROVER_HOME")" "$DROVER_BIN"
mv "$tmp/unpack/drover" "$DROVER_HOME"

ln -sf "$DROVER_HOME/dr" "$DROVER_BIN/dr"
ln -sf "$DROVER_HOME/drover" "$DROVER_BIN/drover"
[ -x "$DROVER_HOME/drover-native" ] && ln -sf "$DROVER_HOME/drover-native" "$DROVER_BIN/drover-native"  # native window (preview)
ln -sf "$DROVER_HOME/dr" "$DROVER_BIN/hd"  # old CLI name, kept for agents and scripts that still call it

# Remove an install made under the old "herd" name (its settings move over on first start).
old_home="$HOME/.local/share/herd"
if [ -x "$old_home/hd" ]; then
  "$old_home/hd" server stop >/dev/null 2>&1 || true
  rm -rf "$old_home"
  rm -f "$DROVER_BIN/herd" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/herd.desktop"
fi

# App-menu entry so drover shows up in the desktop launcher (icon ships inside the bundle).
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icon="$DROVER_HOME/_internal/drover/web/favicon.png"
mkdir -p "$apps"
cat > "$apps/drover.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Drover
Comment=Workspace for running coding agents
Exec=$DROVER_HOME/dr app
Icon=$icon
Terminal=false
Categories=Development;
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$apps" >/dev/null 2>&1 || true

echo "drover: installed to $DROVER_HOME (dr, drover linked in $DROVER_BIN)"
case ":$PATH:" in
  *":$DROVER_BIN:"*) ;;
  *) echo "drover: add $DROVER_BIN to PATH:  export PATH=\"$DROVER_BIN:\$PATH\"" ;;
esac
echo "drover: run 'dr' to start. The window needs WebKitGTK 4.1 (Debian/Ubuntu: libwebkit2gtk-4.1-0); without it 'dr app' opens the web UI in your browser."
