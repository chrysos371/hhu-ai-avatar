#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
workspace_root="$(dirname "$project_root")"
python_bin="$workspace_root/envs/hhu-ai-avatar/bin/python"
if [[ ! -x "$python_bin" ]]; then python_bin="python"; fi
export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
if [[ -d "$workspace_root/runtime/qq-deps/nonebot" ]]; then export PYTHONPATH="$workspace_root/runtime/qq-deps:$PYTHONPATH"; fi
export TMPDIR="$workspace_root/runtime/tmp"
mkdir -p "$TMPDIR"
cd "$project_root"
exec "$python_bin" -m avatar.channels.qq "$@"
