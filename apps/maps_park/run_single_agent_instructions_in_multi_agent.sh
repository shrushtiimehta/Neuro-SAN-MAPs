#!/usr/bin/env bash
# Baseline multi-agent topology, isolated for the single-agent-instructions experiment.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_ARM_NAME=single_agent_instructions_in_multi_agent
export MAPS_RUNNER_AGENT=player
export MAPS_MICRO_AGENT=watcher
export MAPS_MACRO_AGENT=planner
export MAPS_STATE_DIR=state_ablations/single_agent_instructions_in_multi_agent
export MAPS_SEED_DIR=ablation_seeds/single_agent_instructions_in_multi_agent
export MAPS_LOG_DIR=logs/maps_ablation_single_agent_instructions_in_multi_agent
export MAPS_MERGED_CONTEXT=0
export MAPS_AGENT_MANIFEST_FILE="$HERE/../../registries/manifest.hocon"
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_ABLATION_ARM=single_agent_instructions_in_multi_agent
export WANDB_RUN_GROUP=single_agent_instructions_in_multi_agent
export MAPS_RUNNER_MODULE=apps.maps_park.bounded_runner

exec "$HERE/run_ablation_services.sh" "$@"
