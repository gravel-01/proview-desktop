#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
frontend_dir="$repo_root/frontend"

if [ ! -d "$frontend_dir/node_modules" ]; then
  npm install --prefix "$frontend_dir"
fi

export PROVIEW_DESKTOP_BUILD=1
export PROVIEW_API_PORT="${PROVIEW_API_PORT:-18765}"
export VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://127.0.0.1:${PROVIEW_API_PORT}}"

npm --prefix "$frontend_dir" run build
