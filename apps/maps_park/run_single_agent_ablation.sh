#!/usr/bin/env bash
# Run the isolated Single Agent arm with the shared replica-safe service stack.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3050}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8815}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8140}"
export MAPS_ARM_NAME=solo_ablation
export MAPS_RUNNER_AGENT=player_solo
export MAPS_MICRO_AGENT=planner_solo
export MAPS_MACRO_AGENT=planner_solo
export MAPS_STATE_DIR=state_solo
export MAPS_SEED_DIR=ablation_seeds/solo_ablation
export MAPS_LOG_DIR=logs/maps_park_solo
export MAPS_MERGED_CONTEXT=1
# Keep this arm comparable with cold/current-run-only controls. Do not inherit
# MAPS_INCLUDE_ARCHIVED=1 from the caller's shell.
export MAPS_INCLUDE_ARCHIVED=0
export MAPS_AGENT_MANIFEST_FILE="$HERE/../../registries/ablations/single_agent/manifest.hocon"
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_ABLATION_ARM="${MAPS_ABLATION_ARM:-solo_ablation}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$MAPS_ABLATION_ARM}"
export MAPS_RUNNER_MODULE=apps.maps_park.solo_ablation_runner

exec "$HERE/run_ablation_services.sh" "$@"
