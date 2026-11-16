#!/usr/bin/env bash
# Run baseline sub-agents with independent access to the complete park status.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_ARM_NAME=full_status_subagents
export MAPS_RUNNER_AGENT=player_full_status_subagents
export MAPS_MICRO_AGENT=planner_full_status_subagents
export MAPS_MACRO_AGENT=planner_full_status_subagents
export MAPS_STATE_DIR=state_ablations/full_status_subagents
export MAPS_SEED_DIR=ablation_seeds/full_status_subagents
export MAPS_LOG_DIR=logs/maps_ablation_full_status_subagents
export MAPS_MERGED_CONTEXT=0
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_ABLATION_ARM="${MAPS_ABLATION_ARM:-full_status_subagents}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$MAPS_ABLATION_ARM}"
export MAPS_RUNNER_MODULE=apps.maps_park.single_planner_ablation_runner

exec "$HERE/run_ablation_services.sh" "$@"
