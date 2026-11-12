#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
asset_root="${HHU_AVATAR_DATA_ROOT:-$(python3 "$project_root/scripts/project_paths.py")}"
export HHU_AVATAR_DATA_ROOT="$asset_root"
local_node="$asset_root/runtime/node-npm/node_modules/node/bin"
if [[ -x "$local_node/node" ]]; then export PATH="$local_node:$PATH"; fi
node -e 'const [a,b]=process.versions.node.split(".").map(Number);if(a<22||(a===22&&b<12)){console.error("需要 Node.js 22.12+，请先准备本地工具链。");process.exit(1)}'
export NPM_CONFIG_CACHE="$asset_root/cache/npm"
export TMPDIR="$asset_root/tmp"
mkdir -p "$TMPDIR"
if [[ "${1:-}" == "run" && "${2:-}" == "e2e" ]]; then
  export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$asset_root/runtime/playwright}"
  browser_libs="$asset_root/runtime/browser-libs"
  if [[ -d "$browser_libs/extracted/usr/lib/x86_64-linux-gnu" ]]; then export LD_LIBRARY_PATH="$browser_libs/extracted/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"; fi
  if [[ -f "$browser_libs/fontconfig.xml" ]]; then export FONTCONFIG_FILE="$browser_libs/fontconfig.xml"; fi
fi
local_npm="$asset_root/runtime/npm10/package/bin/npm-cli.js"
if [[ "${1:-}" == "install" || "${1:-}" == "ci" ]]; then
  if [[ -f "$asset_root/runtime/npm-registry-ipv4.cjs" ]]; then export NODE_OPTIONS="${NODE_OPTIONS:-} --require=$asset_root/runtime/npm-registry-ipv4.cjs"; fi
fi
if [[ -f "$local_npm" ]]; then exec node "$local_npm" --prefix "$project_root/frontend" "$@"; fi
exec npm --prefix "$project_root/frontend" "$@"
