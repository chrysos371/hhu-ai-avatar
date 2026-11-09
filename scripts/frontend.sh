#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
workspace_root="$(dirname "$project_root")"
local_node="$workspace_root/runtime/node-npm/node_modules/node/bin"
if [[ -x "$local_node/node" ]]; then export PATH="$local_node:$PATH"; fi
node -e 'const [a,b]=process.versions.node.split(".").map(Number);if(a<22||(a===22&&b<12)){console.error("需要 Node.js 22.12+，请先准备本地工具链。");process.exit(1)}'
export NPM_CONFIG_CACHE="$workspace_root/npm-cache"
export TMPDIR="$workspace_root/runtime/tmp"
mkdir -p "$TMPDIR"
if [[ "${1:-}" == "run" && "${2:-}" == "e2e" ]]; then
  export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$workspace_root/runtime/playwright}"
  browser_libs="$workspace_root/runtime/browser-libs"
  if [[ -d "$browser_libs/extracted/usr/lib/x86_64-linux-gnu" ]]; then export LD_LIBRARY_PATH="$browser_libs/extracted/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"; fi
  if [[ -f "$browser_libs/fontconfig.xml" ]]; then export FONTCONFIG_FILE="$browser_libs/fontconfig.xml"; fi
fi
local_npm="$workspace_root/runtime/npm10/package/bin/npm-cli.js"
if [[ "${1:-}" == "install" || "${1:-}" == "ci" ]]; then
  if [[ -f "$workspace_root/runtime/npm-registry-ipv4.cjs" ]]; then export NODE_OPTIONS="${NODE_OPTIONS:-} --require=$workspace_root/runtime/npm-registry-ipv4.cjs"; fi
fi
if [[ -f "$local_npm" ]]; then exec node "$local_npm" --prefix "$project_root/frontend" "$@"; fi
exec npm --prefix "$project_root/frontend" "$@"
