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

# Detect --resume early: on resume the MAPs env continues a mid-flight
# episode, so we must NOT move that episode's run.ep<NNN>.jsonl aside (an
# episode must live in exactly one file). On a fresh start we archive the
# prior run's per-episode logs into a timestamped subdir.
RUN_TS="$(date +%Y%m%d-%H%M%S)"
RESUMING=0
for arg in "$@"; do
    [[ "$arg" == "--resume" ]] && RESUMING=1
done

# studio.log is just a process log — always rotate it.
[[ -s "$LOG_DIR/studio.log" ]] && mv "$LOG_DIR/studio.log" "$LOG_DIR/studio.log.$RUN_TS"

if [[ $RESUMING -eq 0 ]]; then
    # Fresh start: archive prior per-episode run logs + turns.jsonl so the
    # new run begins clean and never appends into a previous run's episode
    # file. strategy/playbook state is untouched (lessons survive).
    shopt -s nullglob
    PRIOR_EPISODE_LOGS=("$LOG_DIR"/run.ep*.jsonl "$LOG_DIR"/run.jsonl)
    archived=0
    if (( ${#PRIOR_EPISODE_LOGS[@]} )) || [[ -s "$LOG_DIR/turns.jsonl" ]]; then
        ARCHIVE_DIR="$LOG_DIR/prior-runs/$RUN_TS"
        mkdir -p "$ARCHIVE_DIR"
        for f in "${PRIOR_EPISODE_LOGS[@]}"; do
            [[ -s "$f" ]] && { mv "$f" "$ARCHIVE_DIR/"; archived=$((archived + 1)); }
        done
        [[ -s "$LOG_DIR/turns.jsonl" ]] && { mv "$LOG_DIR/turns.jsonl" "$ARCHIVE_DIR/"; archived=$((archived + 1)); }
    fi
    shopt -u nullglob
    [[ $archived -gt 0 ]] && echo "Archived $archived prior-run log file(s) to $LOG_DIR/prior-runs/$RUN_TS"
else
    echo "Resuming: keeping existing run.ep*.jsonl so the in-flight episode stays in one file."
fi

export AGENT_MANIFEST_FILE="$STUDIO_DIR/registries/manifest.hocon"
export AGENT_TOOL_PATH="$STUDIO_DIR/coded_tools"
export AGENT_TOOLBOX_INFO_FILE="$STUDIO_DIR/neuro_san_studio/toolbox/toolbox_info.hocon"
export MCP_SERVERS_INFO_FILE="$STUDIO_DIR/neuro_san_studio/mcp/mcp_info.hocon"
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
    local log_target="${4:-$LOG_DIR/$name.log}"
    echo "[$name] starting in $cwd"
    ( cd "$cwd" && eval "$cmd" ) > "$log_target" 2>&1 &
    PIDS+=($!)
}

[[ -d "$MAPS_REPO/map_backend" ]] || { echo "MAPs repo not found at $MAPS_REPO"; exit 1; }
[[ -f "$OPEN_GRIDWORLD/maps_mcp_server.py" ]] || { echo "open_gridworld not found at $OPEN_GRIDWORLD"; exit 1; }

# Kill any leftover processes from a previous run before starting fresh.
# Studio spawns nsflow via uvicorn — that child process keeps port 4183 even
# after the studio parent dies, so we explicitly target it too.
pkill -f "map_backend/server.js"          2>/dev/null || true
pkill -f "maps_mcp_server.py"             2>/dev/null || true
pkill -f "neuro_san_studio"               2>/dev/null || true
pkill -f "nsflow"                         2>/dev/null || true
pkill -f "neuro_san.*run"                 2>/dev/null || true
sleep 2

start "maps_node"   "$MAPS_REPO"       "node map_backend/server.js"
sleep 2
MAPS_STATE_FILE="${MAPS_STATE_FILE:-$STUDIO_DIR/coded_tools/maps_park/state/park_state.pkl}"
MAPS_SNAPSHOT_DIR="${MAPS_SNAPSHOT_DIR:-$STUDIO_DIR/coded_tools/maps_park/state/snapshots}"
mkdir -p "$MAPS_SNAPSHOT_DIR"
# Pass --resume only when the user invoked the script with it; default is fresh.
MAPS_RESUME_FLAG=""
for arg in "$@"; do
    if [[ "$arg" == "--resume" ]]; then
        MAPS_RESUME_FLAG="--resume"
    fi
done
start "maps_mcp"    "$OPEN_GRIDWORLD"  "python maps_mcp_server.py --layout the_islands --difficulty medium --mcp_port 8765 --num_parks 1 --maps_repo_dir '$MAPS_REPO' --state_file '$MAPS_STATE_FILE' --snapshot_dir '$MAPS_SNAPSHOT_DIR' $MAPS_RESUME_FLAG"
sleep 3
start "studio"      "$STUDIO_DIR"      "python -m neuro_san_studio run"
# Wait until studio HTTP endpoint is accepting connections AND both agent
# networks (game-runner + consultant) appear in the registry list.
for i in $(seq 1 60); do
    list_json="$(curl -m 1 -s http://localhost:8090/api/v1/list 2>/dev/null || true)"
    if echo "$list_json" | grep -q '"industry/maps_park"' \
       && echo "$list_json" | grep -q '"industry/maps_park_consultant"'; then
        echo "studio ready after ${i}s (both networks registered)"
        break
    fi
    sleep 1
done

echo
echo "All background services up. Tailing logs at $LOG_DIR."
echo "Starting runner in foreground (Ctrl-C stops everything)."
echo

cd "$STUDIO_DIR"
# Forward all args (including --resume) to the runner. The MCP server already
# consumed --resume above; the runner needs it too, to decide whether to reset
# the playbooks to their config seeds (fresh start) or keep the working copies
# (resume). `set -u` + bash 3 (macOS) trips on an empty array, so guard with ${arr[@]+...}.
python3 -m apps.maps_park.runner ${@+"$@"}
