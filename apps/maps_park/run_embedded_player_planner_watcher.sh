#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3020}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8785}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8110}"
export MAPS_ARM_NAME=embedded_player_planner_watcher
export MAPS_RUNNER_AGENT=player_planner_watcher_embedded
export MAPS_MICRO_AGENT=player_planner_watcher_embedded
export MAPS_MACRO_AGENT=player_planner_watcher_embedded
export MAPS_STATE_DIR=state_ablations/embedded_player_planner_watcher
export MAPS_SEED_DIR=ablation_seeds/embedded_player_planner_watcher
export MAPS_LOG_DIR=logs/maps_ablation_embedded_player_planner_watcher
exec "$HERE/run_ablation_services.sh" "$@"
