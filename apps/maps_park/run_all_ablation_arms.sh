#!/usr/bin/env bash
# Run all eight arms sequentially, exactly 10 completed episodes per arm.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_EPISODE_LIMIT=10

arms=(
    run_player_with_watcher.sh
    run_player_with_planner.sh
    run_embedded_player_planner_watcher.sh
    run_unstructured_player_planner_watcher.sh
    run_g_memory_player_planner_watcher.sh
    run_single_agent_ablation.sh
    run_multi_player_single_planner.sh
    run_single_player_multi_planner_watcher.sh
)

for arm in "${arms[@]}"; do
    echo
    echo "========== $arm: 10 episodes =========="
    "$HERE/$arm" --fresh "$@"
done

echo
echo "All eight ablation arms completed; 80 episodes total."
