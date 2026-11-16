#!/usr/bin/env bash
# Multi-agent player with one planner agent shared across start, periodic, and end analysis.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3060}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8825}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8150}"
export MAPS_ARM_NAME=multi_player_single_planner
export MAPS_RUNNER_AGENT=player_ablation
export MAPS_MICRO_AGENT=planner_single
export MAPS_MACRO_AGENT=planner_single
export MAPS_STATE_DIR=state_ablations/multi_player_single_planner
export MAPS_SEED_DIR=ablation_seeds/multi_player_single_planner
export MAPS_LOG_DIR=logs/maps_ablation_multi_player_single_planner
export MAPS_RUNNER_MODULE=apps.maps_park.single_planner_ablation_runner
exec "$HERE/run_ablation_services.sh" "$@"
