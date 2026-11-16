#!/usr/bin/env bash
# Uniform Qwen 4B model with the canonical multi-agent topology.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3200}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8900}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8200}"
export MAPS_ARM_NAME=qwen4b_multi
export MAPS_RUNNER_AGENT=player
export MAPS_MICRO_AGENT=watcher
export MAPS_MACRO_AGENT=planner
export MAPS_STATE_DIR=state_ablations/qwen4b_multi
export MAPS_SEED_DIR=ablation_seeds/qwen4b_multi
export MAPS_LOG_DIR=logs/maps_ablation_qwen4b_multi
export MAPS_AGENT_MANIFEST_FILE="$HERE/../../registries/ablations/qwen4b_multi/manifest.hocon"
export MAPS_RUNNER_MODULE=apps.maps_park.bounded_runner
export MAPS_MERGED_CONTEXT=0
export MAPS_USE_LAST_REWARD=0
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_ABLATION_ARM="${MAPS_ABLATION_ARM:-qwen4b_multi}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$MAPS_ABLATION_ARM}"
export MAPS_STUDY_ID=maps-model-topology-self-improvement-v1
export MAPS_TOPOLOGY=multi_agent
export MAPS_SELF_IMPROVEMENT=1
export MAPS_MODEL_PROVIDER=ollama
export MAPS_PLAYER_MODEL=qwen3:4b
export MAPS_PLANNER_MODEL=qwen3:4b
export MAPS_WATCHER_MODEL=qwen3:4b
export MAPS_REQUIRED_MODELS=qwen3:4b
export MAPS_MODEL_CONTEXT_TOKENS=32768
export MAPS_WANDB_REQUIRED=1
export MAPS_STUDY_PREFLIGHT="${MAPS_STUDY_PREFLIGHT:-1}"
export MAPS_DEFAULT_FRESH=1
export WANDB_MODE=online

exec "$HERE/run_ablation_services.sh" "$@"
