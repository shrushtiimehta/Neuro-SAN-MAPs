#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3010}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8775}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8100}"
export MAPS_ARM_NAME=player_with_planner
export MAPS_RUNNER_AGENT=player_ablation
export MAPS_MICRO_AGENT=off
export MAPS_MACRO_AGENT=planner_ablation
export MAPS_STATE_DIR=state_ablations/player_with_planner
export MAPS_SEED_DIR=ablation_seeds/player_with_planner
export MAPS_LOG_DIR=logs/maps_ablation_player_with_planner
exec "$HERE/run_ablation_services.sh" "$@"
