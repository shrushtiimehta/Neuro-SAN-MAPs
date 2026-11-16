#!/usr/bin/env bash
# Start a new bounded Baseline run without disturbing concurrent ablation stacks.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Keep the canonical baseline on its established ports. Replica-provided values
# still take precedence when this launcher is used from an isolated checkout.
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3000}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8765}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8090}"
export MAPS_ARM_NAME=baseline
export MAPS_RUNNER_AGENT=player
export MAPS_MICRO_AGENT=watcher
export MAPS_MACRO_AGENT=planner
export MAPS_STATE_DIR=state
export MAPS_SEED_DIR=coded_tools/config_files
export MAPS_LOG_DIR=logs/maps_park
export MAPS_MERGED_CONTEXT=0
export MAPS_USE_LAST_REWARD=0
export MAPS_AGENT_MANIFEST_FILE="$HERE/../../registries/manifest.hocon"
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_ABLATION_ARM=baseline
export WANDB_RUN_GROUP=baseline
export MAPS_RUNNER_MODULE=apps.maps_park.bounded_runner
export MAPS_SKIP_ABLATION_VALIDATION=1

exec "$HERE/run_ablation_services.sh" "$@"
