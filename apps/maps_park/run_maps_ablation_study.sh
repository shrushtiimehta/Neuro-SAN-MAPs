#!/usr/bin/env bash
# Run the complete eight-arm, 80-episode study sequentially.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_EPISODE_LIMIT=10

arms=(
    run_study_qwen4b_multi.sh
    run_study_qwen4b_single.sh
    run_study_qwen4b_strong_planner_multi.sh
    run_study_qwen4b_strong_planner_single.sh
    run_study_no_self_improvement_multi.sh
    run_study_no_self_improvement_single.sh
    run_small_model_baseline.sh
    run_single_agent_gpt5_mini.sh
)

for arm in "${arms[@]}"; do
    echo
    echo "========== $arm: 10 episodes =========="
    "$HERE/$arm" --fresh "$@"
done

echo
echo "All eight MAPS study arms completed; 80 episodes total."
