#!/usr/bin/env bash
# Launch the isolated two-agent baseline. The player network contains one agent;
# the planner network contains one agent and also owns periodic analysis.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MAPS_STATE_DIR=state_solo
export MAPS_LOG_DIR=logs/maps_park_solo
export MAPS_MERGED_CONTEXT=1
export MAPS_RUNNER_MODULE="${MAPS_RUNNER_MODULE:-apps.maps_park.solo_runner}"
export AGENT_MANIFEST_FILE="$SCRIPT_DIR/../../registries/ablations/single_agent/manifest.hocon"

exec "$SCRIPT_DIR/run_all.sh" \
    "$@" \
    --runner-agent player_solo \
    --micro-agent planner_solo \
    --macro-agent planner_solo
