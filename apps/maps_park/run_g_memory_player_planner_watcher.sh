#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_NODE_PORT="${MAPS_NODE_PORT:-3080}"
export MAPS_MCP_PORT="${MAPS_MCP_PORT:-8845}"
export MAPS_STUDIO_PORT="${MAPS_STUDIO_PORT:-8170}"
export MAPS_ARM_NAME=g_memory_player_planner_watcher
export MAPS_RUNNER_AGENT=player_g_memory
export MAPS_MICRO_AGENT=watcher_g_memory
export MAPS_MACRO_AGENT=planner_g_memory
export MAPS_STATE_DIR=state_ablations/g_memory_player_planner_watcher
export MAPS_SEED_DIR=ablation_seeds/g_memory_player_planner_watcher
export MAPS_LOG_DIR=logs/maps_ablation_g_memory_player_planner_watcher
export THINKING_FILE="$MAPS_LOG_DIR/agent_thinking.txt"
export THINKING_DIR="$MAPS_LOG_DIR/thinking_dir"
export THINKING_DIR_SMALL="$MAPS_LOG_DIR/thinking-dir-small"
export MAPS_GMEMORY_NO_SEEDS=1
export MAPS_GMEMORY_REPO="${MAPS_GMEMORY_REPO:-$HOME/GMemory-upstream}"
export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
export MAPS_RUNNER_MODULE=apps.maps_park.g_memory_ablation_runner
expected_gmemory_commit=7b581c51d993bd600df14691d101d7e601040cc6
actual_gmemory_commit="$(git -C "$MAPS_GMEMORY_REPO" rev-parse HEAD 2>/dev/null || true)"
if [[ "$actual_gmemory_commit" != "$expected_gmemory_commit" ]]; then
    echo "ERROR: expected GMemory checkout at $expected_gmemory_commit. Run apps/maps_park/setup_g_memory.sh first."
    exit 1
fi
if ! "$HERE/../../venv/bin/python" -c \
    'import finch, langchain_chroma; from sentence_transformers import SentenceTransformer; SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")' \
    >/dev/null 2>&1; then
    echo "ERROR: GMemory embedding model or dependencies are unavailable. Run apps/maps_park/setup_g_memory.sh first."
    exit 1
fi
exec "$HERE/run_ablation_services.sh" "$@"
