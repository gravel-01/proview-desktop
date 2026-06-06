#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
desktop_dir="$repo_root/desktop"
release_dir="$desktop_dir/release"
log_dir="$repo_root/logs/desktop-package"
timestamp="$(date +%Y%m%d-%H%M%S)"
log_file="$log_dir/desktop-package-mac-$timestamp.log"

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script must be run on macOS. Build the Mac package on your M-series Mac."
  exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
  echo "This script is configured for Apple Silicon. Run it in a native arm64 terminal on your M-series Mac."
  echo "If Terminal is running through Rosetta, disable Rosetta and try again."
  exit 1
fi

mkdir -p "$log_dir"
exec > >(tee -a "$log_file") 2>&1

echo "========================================================================"
echo "ProView Desktop macOS Apple Silicon packaging started"
echo "========================================================================"
echo "Repo: $repo_root"
echo "Desktop: $desktop_dir"
echo "Release: $release_dir"
echo "Log: $log_file"
echo "Python: ${PYTHON:-python3}"
echo

echo "Step 1/3: build frontend"
bash "$desktop_dir/scripts/build-frontend.sh"

echo
echo "Step 2/3: build macOS arm64 backend"
bash "$desktop_dir/scripts/build-backend-macos.sh"

echo
echo "Step 3/3: package macOS app"
if [ "$#" -gt 0 ]; then
  bash "$desktop_dir/scripts/package-app-macos.sh" "$@"
else
  bash "$desktop_dir/scripts/package-app-macos.sh"
fi

echo
echo "========================================================================"
echo "macOS packaging completed"
echo "========================================================================"
echo "Release artifacts:"
find "$release_dir" -maxdepth 1 -type f \( -name "*Mac*.dmg" -o -name "*Mac*.zip" \) -print
echo "Log: $log_file"
