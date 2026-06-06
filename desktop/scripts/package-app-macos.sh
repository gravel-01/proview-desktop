#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
desktop_dir="$(cd "$script_dir/.." && pwd)"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script must be run on macOS to produce a runnable macOS desktop package."
  exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
  echo "This script is configured for Apple Silicon. Run it in a native arm64 terminal on your M-series Mac."
  exit 1
fi

if [ ! -d "$desktop_dir/node_modules" ]; then
  npm install --prefix "$desktop_dir"
fi

export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"

cd "$desktop_dir"

if [ "$#" -gt 0 ]; then
  npx electron-builder "$@" --arm64
else
  npx electron-builder --mac dmg zip --arm64
fi
