#!/usr/bin/env bash
# Ten full multi-agent strategy episodes with no cross-episode carryover.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3240}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8940}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8240}"
export MAPS_ARM_NAME=no_self_improvement_multi
export MAPS_RUNNER_AGENT=player
export MAPS_MICRO_AGENT=watcher
export MAPS_MACRO_AGENT=planner
export MAPS_STATE_DIR=state_ablations/no_self_improvement_multi
export MAPS_SEED_DIR=ablation_seeds/no_self_improvement_multi
export MAPS_LOG_DIR=logs/maps_ablation_no_self_improvement_multi
export MAPS_AGENT_MANIFEST_FILE="$HERE/../../registries/ablations/no_self_improvement_multi/manifest.hocon"
export MAPS_RUNNER_MODULE=apps.maps_park.no_self_improvement_runner
export MAPS_MERGED_CONTEXT=0
export MAPS_USE_LAST_REWARD=0
export MAPS_EPISODE_LIMIT=10
export MAPS_ABLATION_ARM="${MAPS_ABLATION_ARM:-no_self_improvement_multi}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$MAPS_ABLATION_ARM}"
export MAPS_STUDY_ID=maps-model-topology-self-improvement-v1
export MAPS_TOPOLOGY=multi_agent
export MAPS_SELF_IMPROVEMENT=0
export MAPS_NO_CROSS_EPISODE=1
export MAPS_SKIP_MACRO_CLOSEOUT=1
export MAPS_MODEL_PROVIDER=openai
export MAPS_PLAYER_MODEL=gpt-5.5
export MAPS_PLANNER_MODEL=gpt-5.5
export MAPS_WATCHER_MODEL=gpt-5.5
export MAPS_REQUIRED_MODELS=gpt-5.5
export MAPS_WANDB_REQUIRED=1
export MAPS_STUDY_PREFLIGHT="${MAPS_STUDY_PREFLIGHT:-1}"
export MAPS_DEFAULT_FRESH=1
export WANDB_MODE=online

exec "$HERE/run_ablation_services.sh" "$@"
