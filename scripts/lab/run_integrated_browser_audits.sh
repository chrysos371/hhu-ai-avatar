#!/usr/bin/env bash
# Each opt-in gets its own fixture DB/server; privacy probes never share state.
set -euo pipefail
project_root="$(cd "$(dirname "$0")/../.." && pwd)"
output_root="${1:?provide a fresh absolute evidence directory}"
[[ "$output_root" = /* ]] || { printf 'Evidence directory must be absolute\n' >&2; exit 2; }
mkdir "$output_root"
run_case() {
  local name="$1" flag="$2" file="$3"
  mkdir "$output_root/$name"
  printf '%s start\n' "$name"
  env "$flag=1" "AVATAR_E2E_EVIDENCE_DIR=$output_root/$name" \
    "AVATAR_E2E_RUNTIME_EVIDENCE=$output_root/$name-runtime.json" \
    "$project_root/scripts/frontend.sh" run e2e -- "e2e/$file" > "$output_root/$name.log" 2>&1
  printf '%s completed\n' "$name"
}
run_case actions AVATAR_E2E_ACTION_RECEIPTS action-receipts.spec.ts
run_case pcm AVATAR_E2E_PLAYBACK_AUDIT playback-audit.spec.ts
run_case notifications AVATAR_E2E_NOTIFICATION_AUDIT notification-audit.spec.ts
run_case external-erase AVATAR_E2E_EXTERNAL_ERASE external-erase.spec.ts
run_case restore AVATAR_E2E_RESTORE_AUDIT history-restore.spec.ts
run_case history100 AVATAR_E2E_HISTORY_AUDIT history-audit.spec.ts
