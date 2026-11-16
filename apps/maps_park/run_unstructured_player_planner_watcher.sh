#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3030}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8795}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8120}"
export MAPS_ARM_NAME=unstructured_player_planner_watcher
export MAPS_RUNNER_AGENT=player_ablation
export MAPS_MICRO_AGENT=watcher_ablation
export MAPS_MACRO_AGENT=planner_unstructured_learning
export MAPS_STATE_DIR=state_ablations/unstructured_player_planner_watcher
export MAPS_SEED_DIR=ablation_seeds/unstructured_player_planner_watcher
export MAPS_LOG_DIR=logs/maps_ablation_unstructured_player_planner_watcher
exec "$HERE/run_ablation_services.sh" "$@"
