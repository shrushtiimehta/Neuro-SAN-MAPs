#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3040}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8805}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8130}"
export MAPS_ARM_NAME=player_with_watcher
export MAPS_RUNNER_AGENT=player_ablation
export MAPS_MICRO_AGENT=watcher_ablation
export MAPS_MACRO_AGENT=off
export MAPS_STATE_DIR=state_ablations/player_with_watcher
export MAPS_SEED_DIR=ablation_seeds/player_with_watcher
export MAPS_LOG_DIR=logs/maps_ablation_player_with_watcher
exec "$HERE/run_ablation_services.sh" "$@"
