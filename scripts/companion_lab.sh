#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
workspace_root="$(dirname "$project_root")"
python_bin="$workspace_root/envs/hhu-ai-avatar-train/bin/python"
if [[ ! -x "$python_bin" ]]; then python_bin="python"; fi
export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="$workspace_root/hf-cache"
export HF_HUB_CACHE="$workspace_root/hf-cache/hub"
export TORCH_HOME="$workspace_root/runtime/torch-cache"
export TMPDIR="$workspace_root/runtime/tmp"
mkdir -p "$TMPDIR"
cd "$project_root"
exec "$python_bin" -m avatar.lab "$@"
