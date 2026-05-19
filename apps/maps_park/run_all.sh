#!/usr/bin/env bash
# Launches the four processes the maps_park demo needs and tears them all
# down on Ctrl-C. Logs go to ./logs/maps_park/.
#
# Override paths via env vars if your checkouts live elsewhere:
#   MAPS_REPO=/path/to/MAPs OPEN_GRIDWORLD=/path/to/open_gridworld ./run_all.sh

set -euo pipefail

MAPS_REPO="${MAPS_REPO:-$HOME/MAPs}"
OPEN_GRIDWORLD="${OPEN_GRIDWORLD:-$HOME/open_gridworld}"
STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$STUDIO_DIR/logs/maps_park"
MEMORY_DIR="$STUDIO_DIR/memory/maps_park"
mkdir -p "$LOG_DIR" "$MEMORY_DIR"

# Rotate prior-run artifacts in place by appending a timestamp suffix so
# each run starts with empty log + observation files. strategy_memory.json
# is preserved (lessons must survive across runs).
RUN_TS="$(date +%Y%m%d-%H%M%S)"
ROTATE_FILES=(
    "$LOG_DIR/run.jsonl"
    "$LOG_DIR/turns.jsonl"
    "$LOG_DIR/studio.log"
    "$LOG_DIR/maps_mcp.log"
    "$LOG_DIR/maps_node.log"
    "$MEMORY_DIR/latest_observations.json"
)
rotated=0
for f in "${ROTATE_FILES[@]}"; do
    if [[ -s "$f" ]]; then
        mv "$f" "$f.$RUN_TS"
        rotated=$((rotated + 1))
    fi
done
if [[ $rotated -gt 0 ]]; then
    echo "Rotated $rotated prior-run file(s) with suffix .$RUN_TS"
fi

export AGENT_MANIFEST_FILE="$STUDIO_DIR/registries/manifest.hocon"
export AGENT_TOOL_PATH="$STUDIO_DIR/coded_tools"
export AGENT_TOOLBOX_INFO_FILE="$STUDIO_DIR/toolbox/toolbox_info.hocon"
export MCP_SERVERS_INFO_FILE="$STUDIO_DIR/mcp/mcp_info.hocon"
export PYTHONPATH="$STUDIO_DIR${PYTHONPATH:+:$PYTHONPATH}"
echo "AGENT_MANIFEST_FILE=$AGENT_MANIFEST_FILE"
echo "AGENT_TOOL_PATH=$AGENT_TOOL_PATH"

PIDS=()
cleanup() {
    echo
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

start() {
    local name="$1" cwd="$2" cmd="$3"
    echo "[$name] starting in $cwd"
    ( cd "$cwd" && eval "$cmd" ) > "$LOG_DIR/$name.log" 2>&1 &
    PIDS+=($!)
}

[[ -d "$MAPS_REPO/map_backend" ]] || { echo "MAPs repo not found at $MAPS_REPO"; exit 1; }
[[ -f "$OPEN_GRIDWORLD/maps_mcp_server.py" ]] || { echo "open_gridworld not found at $OPEN_GRIDWORLD"; exit 1; }

# Kill any leftover processes from a previous run before starting fresh.
pkill -f "map_backend/server.js" 2>/dev/null || true
pkill -f "maps_mcp_server.py"    2>/dev/null || true
pkill -f "neuro_san.*run"        2>/dev/null || true
sleep 1

start "maps_node"   "$MAPS_REPO"       "node map_backend/server.js"
sleep 2
start "maps_mcp"    "$OPEN_GRIDWORLD"  "python maps_mcp_server.py --layout the_islands --difficulty medium --mcp_port 8765 --num_parks 1 --maps_repo_dir '$MAPS_REPO'"
sleep 3
start "studio"      "$STUDIO_DIR"      "python -m run"
sleep 5

echo
echo "All background services up. Tailing logs at $LOG_DIR."
echo "Starting runner in foreground (Ctrl-C stops everything)."
echo

cd "$STUDIO_DIR"
python -m apps.maps_park.runner "$@"
