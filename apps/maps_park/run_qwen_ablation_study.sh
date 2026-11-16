#!/usr/bin/env bash
# Run the four local-Qwen arms sequentially (40 episodes total).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_EPISODE_LIMIT=10

arms=(
    run_study_qwen4b_multi.sh
    run_study_qwen4b_single.sh
    run_study_qwen4b_strong_planner_multi.sh
    run_study_qwen4b_strong_planner_single.sh
)

for arm in "${arms[@]}"; do
    echo
    echo "========== $arm: 10 episodes =========="
    "$HERE/$arm" --fresh "$@"
done

echo
echo "All four Qwen study arms completed; 40 episodes total."
