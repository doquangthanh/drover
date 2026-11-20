#!/bin/sh
# Assemble the release bundle drover-<os>-<arch>.(tar.gz|zip) from the pieces three repos release at the same tag:
#   drover-core   drover-core-<os>-<arch>.(tar.gz|zip)   dr + dr-py + _internal/
#   drover-web    drover-web-<tag>.tar.gz                web/ + web_dist/ (the UI)
#   drover-web    drover-window-<os>-<arch>[.exe]        the Tauri window, installed as `drover`
#   drover-desktop drover-native-<os>-<arch>[.exe]       the GPUI window
# Each piece has a .sha256 beside it. The layout is the one the updater and launcher.rs expect: `dr` and `_internal/`
# in drover/, the UI in drover/_internal/drover/{web,web_dist}.
#   assemble-bundle.sh <linux|windows> <x64|arm64> <vX.Y.Z> <out-dir>
# Env: DROVER_ASSETS_DIR=<dir with the pieces> (no download: tests, offline), OWNER=doquangthanh.
set -eu

os="$1"; arch="$2"; tag="$3"; out="$4"
owner="${OWNER:-doquangthanh}"
case "$os" in
  linux) ext="tar.gz"; exe="" ;;
  windows) ext="zip"; exe=".exe" ;;
  *) echo "assemble-bundle: os must be linux or windows" >&2; exit 1 ;;
esac
case "$tag" in v[0-9]*) ;; *) echo "assemble-bundle: tag must look like v0.2.0" >&2; exit 1 ;; esac

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/in" "$work/bundle" "$out"

fetch() { # <repo> <asset>: into $work/in, checked against its .sha256
  if [ -n "${DROVER_ASSETS_DIR:-}" ]; then
    cp "$DROVER_ASSETS_DIR/$2" "$work/in/$2"; cp "$DROVER_ASSETS_DIR/$2.sha256" "$work/in/$2.sha256"
  else
    base="https://github.com/$owner/$1/releases/download/$tag/$2"
    curl -fSL --proto '=https' "$base" -o "$work/in/$2"
    curl -fSL --proto '=https' "$base.sha256" -o "$work/in/$2.sha256"
  fi
  want="$(cut -d' ' -f1 "$work/in/$2.sha256")"
  got="$(sha256sum "$work/in/$2" | cut -d' ' -f1)"
  [ "$want" = "$got" ] || { echo "assemble-bundle: checksum mismatch for $2" >&2; exit 1; }
}
unpack() { # <archive> <dir>
  case "$1" in *.zip) unzip -q "$1" -d "$2" ;; *) tar -xzf "$1" -C "$2" ;; esac
}

core="drover-core-$os-$arch.$ext"; web="drover-web-$tag.tar.gz"
window="drover-window-$os-$arch$exe"; native="drover-native-$os-$arch$exe"
fetch drover-core "$core"; fetch drover-web "$web"; fetch drover-web "$window"; fetch drover-desktop "$native"

unpack "$work/in/$core" "$work/bundle"
b="$work/bundle/drover"
[ -f "$b/dr$exe" ] && [ -d "$b/_internal" ] || { echo "assemble-bundle: $core has no drover/dr$exe and drover/_internal" >&2; exit 1; }
mkdir -p "$b/_internal/drover"
tar -xzf "$work/in/$web" -C "$b/_internal/drover"
[ -f "$b/_internal/drover/web_dist/index.html" ] && [ -d "$b/_internal/drover/web" ] || { echo "assemble-bundle: $web has no web/ and web_dist/" >&2; exit 1; }
install -m 755 "$work/in/$window" "$b/drover$exe"
install -m 755 "$work/in/$native" "$b/drover-native$exe"

if [ "$os" = windows ]; then
  (cd "$work/bundle" && zip -qr "$out/drover-windows-$arch.zip" drover)
  cp "$work/in/$window" "$out/drover.exe"  # the download: installs the folder on first run
  asset="drover-windows-$arch.zip"
else
  tar -czf "$out/drover-linux-$arch.tar.gz" -C "$work/bundle" drover
  asset="drover-linux-$arch.tar.gz"
fi
(cd "$out" && sha256sum "$asset" > "$asset.sha256")
echo "assemble-bundle: wrote $out/$asset"
