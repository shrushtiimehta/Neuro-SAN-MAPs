#!/usr/bin/env bash
# Launches the four processes the maps_park demo needs and tears them all
# down on Ctrl-C. Logs go to ./logs/maps_park/.
#
# Override the MAPs repo path via env var if your checkout lives elsewhere:
#   MAPS_REPO=/path/to/MAPs ./run_all.sh
#
# Flags handled here (everything else is forwarded to the runner):
#   --no-archived      telemetry ignores logs/maps_park/prior-runs/ (default).
#   --include-archived telemetry may use prior-runs/ for cross-run comparisons.
#
# Baseline arms. The dedicated launcher selects exactly one player agent and one
# planner agent; the planner also owns periodic analysis. Its state and logs are
# isolated from the multi-agent arm:
#   ./run_all.sh                         # multi-agent player/watcher/planner
#   ./run_solo.sh                        # isolated single-agent registry

set -euo pipefail

MAPS_REPO="${MAPS_REPO:-$HOME/MAPs}"
STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The MAPs MCP server is vendored into this app (was previously an external
# open_gridworld checkout). It is self-contained: only stdlib + mcp/pydantic/
# requests + MAPs' map_py (installed via `pip install -e $MAPS_REPO`).
MAPS_MCP_SERVER="$STUDIO_DIR/apps/maps_park/maps_mcp_server.py"
# LOG_DIR is finalised in the ablation-arm block below, once the arm is known.
MEMORY_DIR="$STUDIO_DIR/memory/maps_park"
mkdir -p "$MEMORY_DIR"

# Boot with the repo venv so `python` (studio/mcp) and `python3` (runner) both
# resolve with deps even if the caller forgot to activate it. Without this a
# fresh start dies at `python: command not found` before the runner can archive
# state. No-op if there is no venv here (PATH is left as-is).
# shellcheck disable=SC1091
[[ -f "$STUDIO_DIR/venv/bin/activate" ]] && source "$STUDIO_DIR/venv/bin/activate"

# Detect --resume early: on resume the MAPs env continues a mid-flight
# episode, so we must NOT move that episode's run.ep<NNN>.jsonl aside (an
# episode must live in exactly one file). On a fresh start we archive the
# prior run's per-episode logs into a timestamped subdir.
RUN_TS="$(date +%Y%m%d-%H%M%S)"

# Archived telemetry is opt-in. Consumed here — the runner has no such arg — and
# passed to the studio process as MAPS_INCLUDE_ARCHIVED.
export MAPS_INCLUDE_ARCHIVED="${MAPS_INCLUDE_ARCHIVED:-0}"
KEPT_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --no-archived) export MAPS_INCLUDE_ARCHIVED=0 ;;
        --include-archived) export MAPS_INCLUDE_ARCHIVED=1 ;;
        *) KEPT_ARGS+=("$arg") ;;
    esac
done
set -- ${KEPT_ARGS[@]+"${KEPT_ARGS[@]}"}
if [[ "$MAPS_INCLUDE_ARCHIVED" == "0" ]]; then
    echo "Archived prior runs EXCLUDED from telemetry (default; best-ever = best in this run)."
else
    echo "Archived prior runs INCLUDED in telemetry (explicit opt-in)."
fi

# ── Ablation arm ───────────────────────────────────────────────────────────
# Which networks the runner drives is the ONLY thing the caller picks; the state
# and log roots follow from it. Both must be exported before studio starts, because
# the coded tools that read them (coded_tools/state_dir.py) live in the STUDIO
# process, not this one or the runner's — which is why this cannot live in the
# runner. Deriving it here also means the arm cannot be run half-configured: a
# single-agent network reading the multi-agent arm's state would silently produce
# a meaningless result rather than an error.
RUNNER_NET="player"; WATCHER_NET="watcher"; MACRO_NET="planner"
DEFAULT_SEED_DISPLAY="coded_tools/config_files"
prev=""
for arg in "$@"; do
    case "$prev" in
        --runner-agent) RUNNER_NET="$arg" ;;
        --micro-agent)  WATCHER_NET="$arg" ;;
        --macro-agent)  MACRO_NET="$arg" ;;
    esac
    case "$arg" in
        --runner-agent=*) RUNNER_NET="${arg#*=}" ;;
        --micro-agent=*)  WATCHER_NET="${arg#*=}" ;;
        --macro-agent=*)  MACRO_NET="${arg#*=}" ;;
    esac
    prev="$arg"
done

if [[ "$RUNNER_NET" == *_solo || "$MACRO_NET" == *_solo ]]; then
    export MAPS_STATE_DIR="${MAPS_STATE_DIR:-state_solo}"
    export MAPS_LOG_DIR="${MAPS_LOG_DIR:-logs/maps_park_solo}"
    export MAPS_RUNNER_MODULE="${MAPS_RUNNER_MODULE:-apps.maps_park.solo_runner}"
    # ONE complete non-learned baseline + ONE planner-written all-domain strategy,
    # ONE merged economics doc, and ONE unpruned status instead of the seven-way
    # split. The coded tools cannot infer this from files on disk, so the arm says
    # so here.
    export MAPS_MERGED_CONTEXT=1
    DEFAULT_SEED_DISPLAY="coded_tools/ablations/single_agent/config_files"
    echo "ARM: SOLO          networks=$RUNNER_NET/$WATCHER_NET/$MACRO_NET  merged context"
    # Both merged inputs are checked in and frozen. Startup validates their
    # presence but never regenerates or rewrites either one.
    [[ -s "$STUDIO_DIR/coded_tools/ablations/single_agent/config_files/seed_playbook_all.md" ]] || {
        echo "Missing frozen solo playbook seed"; exit 1;
    }
    [[ -s "$STUDIO_DIR/coded_tools/ablations/single_agent/config_files/economics_merged.md" ]] || {
        echo "Missing frozen solo economics"; exit 1;
    }
elif [[ "$RUNNER_NET" == *_self_critic ]]; then
    export MAPS_STATE_DIR="${MAPS_STATE_DIR:-state_self_critic}"
    export MAPS_SEED_DIR="${MAPS_SEED_DIR:-$MAPS_STATE_DIR/config_files}"
    export MAPS_LOG_DIR="${MAPS_LOG_DIR:-logs/maps_park_self_critic}"
    echo "ARM: SELF-CRITIQUE networks=$RUNNER_NET/$WATCHER_NET/$MACRO_NET"
elif [[ "$RUNNER_NET" == *_single || "$MACRO_NET" == *_single ]]; then
    export MAPS_STATE_DIR="${MAPS_STATE_DIR:-state_single_agent}"
    export MAPS_SEED_DIR="${MAPS_SEED_DIR:-$MAPS_STATE_DIR/config_files}"
    export MAPS_LOG_DIR="${MAPS_LOG_DIR:-logs/maps_park_single}"
    echo "ARM: SINGLE-AGENT  networks=$RUNNER_NET/$WATCHER_NET/$MACRO_NET"
else
    export MAPS_STATE_DIR="${MAPS_STATE_DIR:-state}"
    export MAPS_LOG_DIR="${MAPS_LOG_DIR:-logs/maps_park}"
    echo "ARM: MULTI-AGENT   networks=$RUNNER_NET/$WATCHER_NET/$MACRO_NET"
fi

# An ablation may supply a private seed mirror. Initialize only missing files:
# confirmed learned rules already written into an existing mirror must survive.
if [[ -n "${MAPS_SEED_DIR:-}" ]]; then
    mkdir -p "$STUDIO_DIR/$MAPS_SEED_DIR"
    copied_seeds=0
    for source in "$STUDIO_DIR/coded_tools/config_files/"seed_playbook_*.md; do
        target="$STUDIO_DIR/$MAPS_SEED_DIR/$(basename "$source")"
        if [[ ! -e "$target" ]]; then
            cp "$source" "$target"
            copied_seeds=$((copied_seeds + 1))
        fi
    done
    [[ $copied_seeds -gt 0 ]] && echo "     initialized $copied_seeds private seed file(s) in $MAPS_SEED_DIR"
fi
echo "     state=$MAPS_STATE_DIR  logs=$MAPS_LOG_DIR  seeds=${MAPS_SEED_DIR:-$DEFAULT_SEED_DISPLAY}"
LOG_DIR="$STUDIO_DIR/$MAPS_LOG_DIR"
mkdir -p "$LOG_DIR" "$STUDIO_DIR/$MAPS_STATE_DIR"

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
    # TSVs and the per-run cost ledger are bucketed alongside the transcripts.
    # park_ids.jsonl is the ONE exception: it is the permanent cumulative ledger
    # (UUID-keyed) and must keep growing across fresh starts, so it is never moved.
    PRIOR_EPISODE_LOGS=("$LOG_DIR"/run.ep*.jsonl "$LOG_DIR"/run.jsonl "$LOG_DIR"/*.tsv)
    [[ -s "$LOG_DIR/episode_cost.jsonl" ]] && PRIOR_EPISODE_LOGS+=("$LOG_DIR/episode_cost.jsonl")
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
    echo "Resuming: keeping local episode files and reconnecting W&B when enabled."
fi

export AGENT_MANIFEST_FILE="${AGENT_MANIFEST_FILE:-$STUDIO_DIR/registries/manifest.hocon}"
export AGENT_TOOL_PATH="$STUDIO_DIR/coded_tools"
export AGENT_TOOLBOX_INFO_FILE="$STUDIO_DIR/neuro_san_studio/toolbox/toolbox_info.hocon"
export MCP_SERVERS_INFO_FILE="$STUDIO_DIR/neuro_san_studio/mcp/mcp_info.hocon"
export PYTHONPATH="$STUDIO_DIR${PYTHONPATH:+:$PYTHONPATH}"
export MAPS_TELEMETRY_BACKEND="${MAPS_TELEMETRY_BACKEND:-wandb}"
export WANDB_PROJECT="${WANDB_PROJECT:-maps-park-ablations}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$(basename "$MAPS_STATE_DIR")}"
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
echo "AGENT_MANIFEST_FILE=$AGENT_MANIFEST_FILE"
echo "AGENT_TOOL_PATH=$AGENT_TOOL_PATH"
echo "TELEMETRY=$MAPS_TELEMETRY_BACKEND  WANDB_PROJECT=$WANDB_PROJECT  GROUP=$WANDB_RUN_GROUP"

PIDS=()
cleanup() {
    echo
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 0' INT TERM

start() {
    local name="$1" cwd="$2" cmd="$3"
    local log_target="${4:-$LOG_DIR/$name.log}"
    echo "[$name] starting in $cwd"
    ( cd "$cwd" && eval "$cmd" ) > "$log_target" 2>&1 &
    PIDS+=($!)
}

[[ -d "$MAPS_REPO/map_backend" ]] || { echo "MAPs repo not found at $MAPS_REPO"; exit 1; }
[[ -f "$MAPS_MCP_SERVER" ]] || { echo "vendored MCP server missing at $MAPS_MCP_SERVER"; exit 1; }

# Kill any leftover processes from a previous run before starting fresh.
# Studio spawns nsflow via uvicorn — that child process keeps port 4183 even
# after the studio parent dies, so we explicitly target it too.
pkill -f "map_backend/server.js"          2>/dev/null || true
pkill -f "maps_mcp_server.py"             2>/dev/null || true
pkill -f "neuro_san_studio"               2>/dev/null || true
pkill -f "nsflow"                         2>/dev/null || true
pkill -f "neuro_san.*run"                 2>/dev/null || true
sleep 2

# --vis mounts the backend's /v1 router, which is the ONLY thing the website
# frontend reads. Without it http://localhost:3001 renders an empty park.
start "maps_node"   "$MAPS_REPO"       "node map_backend/server.js --vis"
sleep 2
MAPS_STATE_FILE="${MAPS_STATE_FILE:-$STUDIO_DIR/$MAPS_STATE_DIR/park_state.pkl}"
MAPS_TRAJECTORY_ARG="--trajectory_dir '$LOG_DIR'"
# Pass --resume only when the user invoked the script with it; default is fresh.
MAPS_RESUME_FLAG=""
for arg in "$@"; do
    if [[ "$arg" == "--resume" ]]; then
        MAPS_RESUME_FLAG="--resume"
    fi
done
start "maps_mcp"    "$STUDIO_DIR"  "python '$MAPS_MCP_SERVER' --layout the_islands --difficulty medium --mcp_port 8765 --num_parks 1 --maps_repo_dir '$MAPS_REPO' --state_file '$MAPS_STATE_FILE' $MAPS_TRAJECTORY_ARG $MAPS_RESUME_FLAG"
sleep 3
start "studio"      "$STUDIO_DIR"      "python -m neuro_san_studio run"
# Wait until studio HTTP endpoint is accepting connections AND all three agent
# networks the runner uses (game-runner + micro + macro analyzers) appear in
# the registry list.
studio_ready=0
registered_or_off() {
    local network="$1"
    case "${network,,}" in
        ""|none|off|disabled) return 0 ;;
    esac
    echo "$list_json" | grep -Eq "\"agent_name\"[[:space:]]*:[[:space:]]*\"$network\""
}
for i in $(seq 1 60); do
    list_json="$(curl -m 1 -s http://localhost:8090/api/v1/list 2>/dev/null || true)"
    if registered_or_off "$RUNNER_NET" \
       && registered_or_off "$WATCHER_NET" \
       && registered_or_off "$MACRO_NET"; then
        echo "studio ready after ${i}s (runner + micro + macro networks registered)"
        studio_ready=1
        break
    fi
    sleep 1
done

if [[ $studio_ready -ne 1 ]]; then
    echo "ERROR: Studio did not register every required network: $RUNNER_NET / $WATCHER_NET / $MACRO_NET"
    echo "Registered response: ${list_json:-<unavailable>}"
    echo "See $LOG_DIR/studio.log for the registry validation error."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    exit 1
fi

echo
echo "All background services up. Tailing logs at $LOG_DIR."
echo "Starting runner in foreground (Ctrl-C stops everything)."
echo

cd "$STUDIO_DIR"
# Forward all args (including --resume) to the runner. The MCP server already
# consumed --resume above; the runner needs it too, to decide whether to reset
# the playbooks to their config seeds (fresh start) or keep the working copies
# (resume). `set -u` + bash 3 (macOS) trips on an empty array, so guard with ${arr[@]+...}.
RUNNER_MODULE="${MAPS_RUNNER_MODULE:-apps.maps_park.bounded_runner}"
python3 -m "$RUNNER_MODULE" ${@+"$@"}
