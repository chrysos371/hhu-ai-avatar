#!/usr/bin/env bash
# Source from project launchers; never change the user's HOME or shared caches.
hhu_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
asset_root="${HHU_AVATAR_DATA_ROOT:-$(python3 -B "$hhu_script_dir/project_paths.py")}"
export HHU_AVATAR_DATA_ROOT="$asset_root"
export TMPDIR="$asset_root/tmp"
export PIP_CACHE_DIR="$asset_root/cache/pip"
export XDG_CACHE_HOME="$asset_root/cache/xdg"
export HF_HOME="$asset_root/cache/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export TORCH_HOME="$asset_root/cache/torch"
export MPLCONFIGDIR="$asset_root/cache/matplotlib"
export NUMBA_CACHE_DIR="$asset_root/cache/numba"
export PYTHONPYCACHEPREFIX="$asset_root/cache/pycache"
mkdir -p "$TMPDIR" "$PIP_CACHE_DIR" "$XDG_CACHE_HOME" "$HF_HUB_CACHE" \
  "$TORCH_HOME" "$MPLCONFIGDIR" "$NUMBA_CACHE_DIR" "$PYTHONPYCACHEPREFIX"
