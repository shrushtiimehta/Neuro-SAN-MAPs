#!/usr/bin/env bash
# Replay state_1.8M (ep3's champion inputs) with the PLANNER OFF: player +
# watcher only, fresh park at episode 0. Same services as run_all.sh, minus the
# run-mode flags that don't apply here.
#
#   ./apps/maps_park/run_replay.sh                 # restore state_1.8M, then play
#   ./apps/maps_park/run_replay.sh --keep-state    # play state/ exactly as it is
#
# Episode 0 matters: ActiveTrials withholds trials older than current_episode-1,
# so state_1.8M's `ep=3` trials only parse on a fresh park (state_1.8M/README.md).
# Anything else on the command line is forwarded to replay_runner.

set -euo pipefail

MAPS_REPO="${MAPS_REPO:-$HOME/MAPs}"
STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAPS_MCP_SERVER="$STUDIO_DIR/apps/maps_park/maps_mcp_server.py"
LOG_DIR="$STUDIO_DIR/logs/maps_park"
mkdir -p "$LOG_DIR" "$STUDIO_DIR/memory/maps_park"
cd "$STUDIO_DIR"

# shellcheck disable=SC1091
[[ -f venv/bin/activate ]] && source venv/bin/activate

RESTORE=1
KEPT_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --keep-state) RESTORE=0 ;;
        *) KEPT_ARGS+=("$arg") ;;
    esac
done
set -- ${KEPT_ARGS[@]+"${KEPT_ARGS[@]}"}

[[ -d "$MAPS_REPO/map_backend" ]] || { echo "MAPs repo not found at $MAPS_REPO"; exit 1; }
[[ -f "$MAPS_MCP_SERVER" ]] || { echo "vendored MCP server missing at $MAPS_MCP_SERVER"; exit 1; }

RUN_TS="$(date +%Y%m%d-%H%M%S)"
# Fresh park at ep0 writes run.ep000.jsonl, so move any prior run's episode logs
# aside first — an episode must live in exactly one file. park_ids.jsonl is the
# permanent cumulative ledger and is never moved (same rule as run_all.sh).
shopt -s nullglob
PRIOR=("$LOG_DIR"/run.ep*.jsonl "$LOG_DIR"/run.jsonl "$LOG_DIR"/*.tsv "$LOG_DIR"/turns.jsonl)
if (( ${#PRIOR[@]} )); then
    ARCHIVE_DIR="$LOG_DIR/prior-runs/$RUN_TS"
    mkdir -p "$ARCHIVE_DIR"
    for f in "${PRIOR[@]}"; do [[ -s "$f" ]] && mv "$f" "$ARCHIVE_DIR/"; done
    echo "Archived prior-run logs to $ARCHIVE_DIR"
fi
shopt -u nullglob
[[ -s "$LOG_DIR/studio.log" ]] && mv "$LOG_DIR/studio.log" "$LOG_DIR/studio.log.$RUN_TS"

# restore.sh overwrites state/playbook_*.md and the trial ledgers with ep3's.
# Champions from earlier runs survive in state/playbook_history/.
if (( RESTORE )); then
    ./state_1.8M/restore.sh
else
    echo "--keep-state: state/ left untouched."
fi

export AGENT_MANIFEST_FILE="$STUDIO_DIR/registries/manifest.hocon"
export AGENT_TOOL_PATH="$STUDIO_DIR/coded_tools"
export AGENT_TOOLBOX_INFO_FILE="$STUDIO_DIR/neuro_san_studio/toolbox/toolbox_info.hocon"
export MCP_SERVERS_INFO_FILE="$STUDIO_DIR/neuro_san_studio/mcp/mcp_info.hocon"
export PYTHONPATH="$STUDIO_DIR${PYTHONPATH:+:$PYTHONPATH}"
export MAPS_INCLUDE_ARCHIVED="${MAPS_INCLUDE_ARCHIVED:-0}"

PIDS=()
cleanup() {
    echo
    echo "Shutting down..."
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do kill "$pid" 2>/dev/null || true; done
    wait 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

start() {
    echo "[$1] starting in $2"
    ( cd "$2" && eval "$3" ) > "$LOG_DIR/$1.log" 2>&1 &
    PIDS+=($!)
}

pkill -f "map_backend/server.js"  2>/dev/null || true
pkill -f "maps_mcp_server.py"     2>/dev/null || true
pkill -f "neuro_san_studio"       2>/dev/null || true
pkill -f "nsflow"                 2>/dev/null || true
pkill -f "neuro_san.*run"         2>/dev/null || true
sleep 2

# --vis mounts the /v1 router the website frontend reads (localhost:3001).
start "maps_node" "$MAPS_REPO" "node map_backend/server.js --vis"
sleep 2
MAPS_STATE_FILE="${MAPS_STATE_FILE:-$STUDIO_DIR/state/park_state.pkl}"
# No --resume: fresh park, episode 0.
start "maps_mcp" "$STUDIO_DIR" "python '$MAPS_MCP_SERVER' --layout the_islands --difficulty medium --mcp_port 8765 --num_parks 1 --maps_repo_dir '$MAPS_REPO' --state_file '$MAPS_STATE_FILE' --trajectory_dir '$LOG_DIR'"
sleep 3
start "studio" "$STUDIO_DIR" "python -m neuro_san_studio run"

# Only the two networks this run uses; the planner is never opened.
for i in $(seq 1 60); do
    list_json="$(curl -m 1 -s http://localhost:8090/api/v1/list 2>/dev/null || true)"
    if echo "$list_json" | grep -q '"player"' && echo "$list_json" | grep -q '"watcher"'; then
        echo "studio ready after ${i}s (player + watcher registered)"
        break
    fi
    sleep 1
done

echo
echo "Replaying with the planner OFF. Ctrl-C stops everything."
echo
python3 -m apps.maps_park.replay_runner ${@+"$@"}
