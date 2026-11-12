#!/usr/bin/env bash
set -euo pipefail
project_root=$(git rev-parse --show-toplevel)
output=${1:?Use a fresh absolute output directory}
[[ "$output" = /* && ! -e "$output" ]] || { echo 'Output must be fresh and absolute' >&2; exit 2; }
mkdir -p "$output"
for scenario in normal_claim response_drop_after_commit navigation_before_response ack_response_drop_after_commit; do
  mkdir "$output/$scenario"
  AVATAR_E2E_REMINDER_DELIVERY_CASE="$scenario" AVATAR_E2E_EMPTY_PROFILE=1 \
  AVATAR_E2E_EVIDENCE_DIR="$output/$scenario" AVATAR_E2E_RUNTIME_EVIDENCE="$output/$scenario-runtime.json" \
    "$project_root/scripts/frontend.sh" run e2e -- e2e/reminder-delivery-recovery.spec.ts > "$output/$scenario.log" 2>&1
  echo "$scenario completed"
done
