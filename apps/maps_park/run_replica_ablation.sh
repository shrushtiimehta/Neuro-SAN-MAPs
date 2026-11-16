#!/usr/bin/env bash
# Run the ablation arm assigned to this isolated repository replica.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTANCE_FILE="$ROOT/.ablation-instance.env"

if [[ ! -f "$INSTANCE_FILE" ]]; then
    echo "ERROR: missing $INSTANCE_FILE"
    exit 1
fi

# The instance file owns replica identity and ports. The episode limit is a
# per-launch control, so an explicit terminal override must survive sourcing
# the instance defaults (for example, resuming an 11-episode run to episode 12).
episode_limit_override="${MAPS_EPISODE_LIMIT-}"
set -a
# shellcheck disable=SC1090
source "$INSTANCE_FILE"
set +a
if [[ -n "$episode_limit_override" ]]; then
    export MAPS_EPISODE_LIMIT="$episode_limit_override"
fi
unset episode_limit_override

: "${MAPS_REPLICA_ID:?MAPS_REPLICA_ID is required}"
: "${MAPS_ABLATION_ARM:?MAPS_ABLATION_ARM is required}"
: "${MAPS_ARM_SCRIPT:?MAPS_ARM_SCRIPT is required}"
: "${MAPS_NODE_PORT:?MAPS_NODE_PORT is required}"
: "${MAPS_MCP_PORT:?MAPS_MCP_PORT is required}"
: "${MAPS_STUDIO_PORT:?MAPS_STUDIO_PORT is required}"

case "$MAPS_ARM_SCRIPT" in
    run_player_with_watcher.sh|run_player_with_planner.sh|run_embedded_player_planner_watcher.sh) ;;
    run_unstructured_player_planner_watcher.sh|run_g_memory_player_planner_watcher.sh) ;;
    run_single_agent_ablation.sh) ;;
    run_multi_player_single_planner.sh|run_single_player_multi_planner_watcher.sh) ;;
    run_small_model_baseline.sh|run_single_agent_gpt5_mini.sh) ;;
    run_single_agent_instructions_in_multi_agent.sh|run_full_status_subagents.sh) ;;
    run_study_qwen4b_multi.sh|run_study_qwen4b_single.sh) ;;
    run_study_qwen4b_strong_planner_multi.sh|run_study_qwen4b_strong_planner_single.sh) ;;
    run_study_no_self_improvement_multi.sh|run_study_no_self_improvement_single.sh) ;;
    *) echo "ERROR: unsupported MAPS_ARM_SCRIPT=$MAPS_ARM_SCRIPT"; exit 1 ;;
esac

echo "[replica] id=$MAPS_REPLICA_ID arm=$MAPS_ABLATION_ARM root=$ROOT"
exec "$ROOT/apps/maps_park/$MAPS_ARM_SCRIPT" "$@"
