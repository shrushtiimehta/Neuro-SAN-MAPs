#!/usr/bin/env bash
# One player agent with the canonical multi-agent planner and watcher networks.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3070}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8835}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8160}"
export MAPS_ARM_NAME=single_player_multi_planner_watcher
export MAPS_RUNNER_AGENT=player_single
export MAPS_MICRO_AGENT=watcher_ablation
export MAPS_MACRO_AGENT=planner_ablation
export MAPS_STATE_DIR=state_ablations/single_player_multi_planner_watcher
export MAPS_SEED_DIR=ablation_seeds/single_player_multi_planner_watcher
export MAPS_LOG_DIR=logs/maps_ablation_single_player_multi_planner_watcher
exec "$HERE/run_ablation_services.sh" "$@"
