#!/usr/bin/env bash
# Run JUST the macro consultant (maps_park_macro) one time, against the
# latest episode log — e.g. to close out a half-episode you cancelled with Ctrl-C
# (which tore the services down).
#
# It boots the same backend run_all.sh needs (MAPs node + MCP env + studio), but
# in RESUME mode: the MCP env continues the cancelled mid-flight episode and the
# episode's run.ep<NNN>.jsonl / turns.jsonl are KEPT (never archived) so the macro
# has them to analyze. It then invokes the macro close-out once and tears the
# services back down.
#
# The macro's episode_end path owns the FULL close-out: cross-run analysis +
# promote/resolve trials + advance_episode. Running this therefore advances the
# episode and may edit the playbooks — the same side effects as a normal episode
# end. It is not a read-only analysis.
#
# Override paths via env vars, as with run_all.sh:
#   MAPS_REPO=/path/to/MAPs OPEN_GRIDWORLD=/path/to/open_gridworld ./run_macro.sh

set -euo pipefail

MAPS_REPO="${MAPS_REPO:-$HOME/MAPs}"
OPEN_GRIDWORLD="${OPEN_GRIDWORLD:-$HOME/open_gridworld}"
STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="$STUDIO_DIR/logs/maps_park"
MEMORY_DIR="$STUDIO_DIR/memory/maps_park"
mkdir -p "$LOG_DIR" "$MEMORY_DIR"

RUN_TS="$(date +%Y%m%d-%H%M%S)"
# studio.log is just a process log — rotate it. We deliberately do NOT touch
# run.ep*.jsonl / turns.jsonl: the macro must read the cancelled episode that
# lives in them (unlike run_all.sh's fresh-start archive step).
[[ -s "$LOG_DIR/studio.log" ]] && mv "$LOG_DIR/studio.log" "$LOG_DIR/studio.log.$RUN_TS"

export AGENT_MANIFEST_FILE="$STUDIO_DIR/registries/manifest.hocon"
export AGENT_TOOL_PATH="$STUDIO_DIR/coded_tools"
export AGENT_TOOLBOX_INFO_FILE="$STUDIO_DIR/neuro_san_studio/toolbox/toolbox_info.hocon"
export MCP_SERVERS_INFO_FILE="$STUDIO_DIR/neuro_san_studio/mcp/mcp_info.hocon"
export PYTHONPATH="$STUDIO_DIR${PYTHONPATH:+:$PYTHONPATH}"
echo "AGENT_MANIFEST_FILE=$AGENT_MANIFEST_FILE"

PIDS=()
cleanup() {
    echo
    echo "Shutting down..."
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
# Tear the services down whether the macro run finishes, errors, or is Ctrl-C'd.
trap cleanup INT TERM EXIT

start() {
    local name="$1" cwd="$2" cmd="$3"
    local log_target="${4:-$LOG_DIR/$name.log}"
    echo "[$name] starting in $cwd"
    ( cd "$cwd" && eval "$cmd" ) > "$log_target" 2>&1 &
    PIDS+=($!)
}

[[ -d "$MAPS_REPO/map_backend" ]] || { echo "MAPs repo not found at $MAPS_REPO"; exit 1; }
[[ -f "$OPEN_GRIDWORLD/maps_mcp_server.py" ]] || { echo "open_gridworld not found at $OPEN_GRIDWORLD"; exit 1; }

# Clear any leftover processes from the cancelled run before booting fresh.
pkill -f "map_backend/server.js"  2>/dev/null || true
pkill -f "maps_mcp_server.py"     2>/dev/null || true
pkill -f "neuro_san_studio"       2>/dev/null || true
pkill -f "nsflow"                 2>/dev/null || true
pkill -f "neuro_san.*run"         2>/dev/null || true
sleep 2

start "maps_node" "$MAPS_REPO" "node map_backend/server.js"
sleep 2
MAPS_STATE_FILE="${MAPS_STATE_FILE:-$STUDIO_DIR/coded_tools/maps_park/state/park_state.pkl}"
MAPS_SNAPSHOT_DIR="${MAPS_SNAPSHOT_DIR:-$STUDIO_DIR/coded_tools/maps_park/state/snapshots}"
mkdir -p "$MAPS_SNAPSHOT_DIR"
# --resume so the env continues the cancelled mid-flight episode instead of
# starting a new one; advance_episode in the close-out then acts on that state.
start "maps_mcp" "$OPEN_GRIDWORLD" "python maps_mcp_server.py --layout the_islands --difficulty medium --mcp_port 8765 --num_parks 1 --maps_repo_dir '$MAPS_REPO' --state_file '$MAPS_STATE_FILE' --snapshot_dir '$MAPS_SNAPSHOT_DIR' --resume"
sleep 3
start "studio" "$STUDIO_DIR" "python -m neuro_san_studio run"

# Wait until studio is accepting connections AND the macro network is registered.
for i in $(seq 1 60); do
    list_json="$(curl -m 1 -s http://localhost:8090/api/v1/list 2>/dev/null || true)"
    if echo "$list_json" | grep -q '"maps_park_macro"'; then
        echo "studio ready after ${i}s (macro network registered)"
        break
    fi
    sleep 1
done

echo
echo "Invoking the macro consultant once (full close-out) on the latest episode."
echo

cd "$STUDIO_DIR"
# --consult-only macro: no game loop, no fresh-start resets; one episode_end call.
python3 -m apps.maps_park.runner --consult-only macro
