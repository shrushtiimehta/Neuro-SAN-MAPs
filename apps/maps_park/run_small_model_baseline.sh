#!/usr/bin/env bash
# Baseline player/planner/watcher topology with GPT-5 Mini for every LLM agent.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3260}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8960}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8260}"
export MAPS_ARM_NAME=baseline_gpt5_mini
export MAPS_RUNNER_AGENT=player
export MAPS_MICRO_AGENT=watcher
export MAPS_MACRO_AGENT=planner
export MAPS_STATE_DIR=state_ablations/baseline_gpt5_mini
export MAPS_SEED_DIR=ablation_seeds/baseline_gpt5_mini
export MAPS_LOG_DIR=logs/maps_ablation_baseline_gpt5_mini
export MAPS_AGENT_MANIFEST_FILE="$HERE/../../registries/ablations/baseline_gpt5_mini/manifest.hocon"
export MAPS_RUNNER_MODULE=apps.maps_park.bounded_runner
export MAPS_MERGED_CONTEXT=0
export MAPS_USE_LAST_REWARD=0
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_ABLATION_ARM="${MAPS_ABLATION_ARM:-baseline_gpt5_mini}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$MAPS_ABLATION_ARM}"
export MAPS_STUDY_ID=maps-model-topology-self-improvement-v1
export MAPS_TOPOLOGY=multi_agent
export MAPS_SELF_IMPROVEMENT=1
export MAPS_MODEL_PROVIDER=openai
export MAPS_PLAYER_MODEL=gpt-5-mini
export MAPS_PLANNER_MODEL=gpt-5-mini
export MAPS_WATCHER_MODEL=gpt-5-mini
export MAPS_REQUIRED_MODELS=gpt-5-mini
export MAPS_WANDB_REQUIRED=1
export MAPS_STUDY_PREFLIGHT="${MAPS_STUDY_PREFLIGHT:-1}"
export MAPS_DEFAULT_FRESH=1
export WANDB_MODE=online

python3 -m apps.maps_park.validate_small_model_baseline
exec "$HERE/run_ablation_services.sh" "$@"
