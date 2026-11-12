#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
asset_root="${HHU_AVATAR_DATA_ROOT:-$(python3 "$project_root/scripts/project_paths.py")}"
export HHU_AVATAR_DATA_ROOT="$asset_root"
python_bin="$asset_root/envs/hhu-ai-avatar-train/bin/python"
if [[ ! -x "$python_bin" ]]; then python_bin="$asset_root/envs/hhu-ai-avatar/bin/python"; fi
export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
export HF_HOME="$asset_root/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export TORCH_HOME="$asset_root/cache/torch"
export TMPDIR="$asset_root/tmp"
mkdir -p "$TMPDIR"
cd "$project_root"
exec "$python_bin" -m avatar.lab "$@"
