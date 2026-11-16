#!/usr/bin/env bash
# Shared isolated service stack for the multi-network MAPs ablation launchers.

set -euo pipefail

STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MAPS_REPO="${MAPS_REPO:-$HOME/MAPs}"
MAPS_MCP_SERVER="$STUDIO_DIR/apps/maps_park/maps_mcp_server.py"

: "${MAPS_ARM_NAME:?MAPS_ARM_NAME is required}"
: "${MAPS_RUNNER_AGENT:?MAPS_RUNNER_AGENT is required}"
: "${MAPS_MICRO_AGENT:?MAPS_MICRO_AGENT is required}"
: "${MAPS_MACRO_AGENT:?MAPS_MACRO_AGENT is required}"
: "${MAPS_STATE_DIR:?MAPS_STATE_DIR is required}"
: "${MAPS_SEED_DIR:?MAPS_SEED_DIR is required}"
: "${MAPS_LOG_DIR:?MAPS_LOG_DIR is required}"

# shellcheck disable=SC1091
[[ -f "$STUDIO_DIR/venv/bin/activate" ]] && source "$STUDIO_DIR/venv/bin/activate"

[[ -d "$MAPS_REPO/map_backend" ]] || { echo "ERROR: MAPs repo not found at $MAPS_REPO"; exit 1; }
[[ -f "$MAPS_MCP_SERVER" ]] || { echo "ERROR: missing $MAPS_MCP_SERVER"; exit 1; }

export AGENT_MANIFEST_FILE="${MAPS_AGENT_MANIFEST_FILE:-$STUDIO_DIR/registries/ablations/$MAPS_ARM_NAME/manifest.hocon}"
export AGENT_TOOL_PATH="$STUDIO_DIR/coded_tools"
export AGENT_TOOLBOX_INFO_FILE="$STUDIO_DIR/neuro_san_studio/toolbox/toolbox_info.hocon"
export MCP_SERVERS_INFO_FILE="$STUDIO_DIR/neuro_san_studio/mcp/mcp_info.hocon"
export PYTHONPATH="$STUDIO_DIR${PYTHONPATH:+:$PYTHONPATH}"
export MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"
export MAPS_MERGED_CONTEXT="${MAPS_MERGED_CONTEXT:-0}"
# LangChain routes ChatOpenAI through /v1/responses when this output format is
# selected. Keep it overridable for diagnostics, but make Responses the default
# for GPT-5.5 reasoning + function-tool workloads.
export LC_OUTPUT_VERSION="${LC_OUTPUT_VERSION:-responses/v1}"
export MAPS_TELEMETRY_BACKEND="${MAPS_TELEMETRY_BACKEND:-wandb}"
export WANDB_PROJECT="${WANDB_PROJECT:-maps-park-ablations}"
export MAPS_ABLATION_ARM="${MAPS_ABLATION_ARM:-$MAPS_ARM_NAME}"
export WANDB_RUN_GROUP="${WANDB_RUN_GROUP:-$MAPS_ABLATION_ARM}"
export MAPS_INCLUDE_ARCHIVED="${MAPS_INCLUDE_ARCHIVED:-0}"

[[ -f "$AGENT_MANIFEST_FILE" ]] || { echo "ERROR: missing ablation manifest $AGENT_MANIFEST_FILE"; exit 1; }

# Each arm launcher owns a unique default triplet. An isolated replica may
# override it through .ablation-instance.env, but falling back to the baseline
# here would make a direct arm launch collide with the baseline stack.
: "${MAPS_NODE_PORT:?MAPS_NODE_PORT must be set by the arm launcher or replica instance}"
: "${MAPS_MCP_PORT:?MAPS_MCP_PORT must be set by the arm launcher or replica instance}"
: "${MAPS_STUDIO_PORT:?MAPS_STUDIO_PORT must be set by the arm launcher or replica instance}"
for port_name in MAPS_NODE_PORT MAPS_MCP_PORT MAPS_STUDIO_PORT; do
    port_value="${!port_name}"
    if [[ ! "$port_value" =~ ^[0-9]+$ ]] \
       || (( 10#$port_value < 1 || 10#$port_value > 65535 )); then
        echo "ERROR: $port_name must be an integer from 1 to 65535; got '$port_value'."
        exit 1
    fi
done
if [[ "$MAPS_NODE_PORT" == "$MAPS_MCP_PORT" \
   || "$MAPS_NODE_PORT" == "$MAPS_STUDIO_PORT" \
   || "$MAPS_MCP_PORT" == "$MAPS_STUDIO_PORT" ]]; then
    echo "ERROR: MAPS_NODE_PORT, MAPS_MCP_PORT, and MAPS_STUDIO_PORT must be unique."
    exit 1
fi
# MAPS_MCP_URL is consumed by both the Studio coded tools and the runner-side
# dispatcher.
export MAPS_MCP_URL="${MAPS_MCP_URL:-http://localhost:${MAPS_MCP_PORT}/mcp}"

LOG_DIR="$STUDIO_DIR/$MAPS_LOG_DIR"
STATE_DIR="$STUDIO_DIR/$MAPS_STATE_DIR"
SEED_DIR="$STUDIO_DIR/$MAPS_SEED_DIR"
mkdir -p "$LOG_DIR" "$STATE_DIR" "$SEED_DIR"

# --fresh archives every child of STATE_DIR. A seed mirror below STATE_DIR
# would therefore disappear immediately before SeedPlaybooks reads it.
if [[ "$SEED_DIR" == "$STATE_DIR" || "$SEED_DIR" == "$STATE_DIR/"* ]]; then
    echo "ERROR: MAPS_SEED_DIR must be outside MAPS_STATE_DIR; --fresh would archive the seeds."
    exit 1
fi

# Each arm gets a private seed mirror. Copy only missing files so any legitimate
# learned canonical rules within that arm survive a resume/default continuation.
merged_context="$(printf '%s' "$MAPS_MERGED_CONTEXT" | tr '[:upper:]' '[:lower:]')"
case "$merged_context" in
    1|true|yes|on)
        SEED_SOURCE_DIR="$STUDIO_DIR/coded_tools/ablations/single_agent/config_files"
        required_seeds=(seed_playbook_all.md)
        ;;
    *)
        SEED_SOURCE_DIR="$STUDIO_DIR/coded_tools/config_files"
        required_seeds=(
            seed_playbook_coordinator.md
            seed_playbook_rides.md
            seed_playbook_shops.md
            seed_playbook_staff.md
            seed_playbook_survey.md
            seed_playbook_research.md
            seed_playbook_layout.md
        )
        ;;
esac
copied=0
if [[ "${MAPS_GMEMORY_NO_SEEDS:-0}" != "1" ]]; then
    for source in "$SEED_SOURCE_DIR/"seed_playbook_*.md; do
        target="$SEED_DIR/$(basename "$source")"
        if [[ ! -e "$target" ]]; then
            cp "$source" "$target"
            copied=$((copied + 1))
        fi
    done
    for required_seed in "${required_seeds[@]}"; do
        [[ -s "$SEED_DIR/$required_seed" ]] || {
            echo "ERROR: required playbook seed is missing or empty: $SEED_DIR/$required_seed"
            exit 1
        }
    done
fi

RUN_TS="$(date +%Y%m%d-%H%M%S)"
RUNNER_ARGS=()
RESUMING=0
EXPLICIT_MODE=0
for arg in "$@"; do
    case "$arg" in
        --no-archived) export MAPS_INCLUDE_ARCHIVED=0 ;;
        --include-archived) export MAPS_INCLUDE_ARCHIVED=1 ;;
        --resume) RESUMING=1; EXPLICIT_MODE=1; RUNNER_ARGS+=("$arg") ;;
        --fresh) EXPLICIT_MODE=1; RUNNER_ARGS+=("$arg") ;;
        *) RUNNER_ARGS+=("$arg") ;;
    esac
done
if [[ $EXPLICIT_MODE -eq 0 && "${MAPS_DEFAULT_FRESH:-0}" == "1" ]]; then
    RUNNER_ARGS=(--fresh "${RUNNER_ARGS[@]}")
fi

[[ -s "$LOG_DIR/studio.log" ]] && mv "$LOG_DIR/studio.log" "$LOG_DIR/studio.log.$RUN_TS"
if [[ $RESUMING -eq 0 ]]; then
    shopt -s nullglob
    prior=("$LOG_DIR"/run.ep*.jsonl "$LOG_DIR"/run.jsonl "$LOG_DIR"/turns.jsonl "$LOG_DIR"/*.tsv "$LOG_DIR"/episode_cost.jsonl)
    archive="$LOG_DIR/prior-runs/$RUN_TS"
    moved=0
    for path in "${prior[@]}"; do
        if [[ -s "$path" && "$(basename "$path")" != "park_ids.jsonl" ]]; then
            mkdir -p "$archive"
            mv "$path" "$archive/"
            moved=$((moved + 1))
        fi
    done
    shopt -u nullglob
    [[ $moved -gt 0 ]] && echo "[ablation] Archived $moved prior log file(s) to $archive"
fi

echo "[ablation] arm=$MAPS_ARM_NAME episodes=$MAPS_EPISODE_LIMIT"
echo "[ablation] networks=$MAPS_RUNNER_AGENT / $MAPS_MICRO_AGENT / $MAPS_MACRO_AGENT"
echo "[ablation] state=$MAPS_STATE_DIR logs=$MAPS_LOG_DIR seeds=$MAPS_SEED_DIR copied_seeds=$copied"
echo "[ablation] telemetry=$MAPS_TELEMETRY_BACKEND project=$WANDB_PROJECT group=$WANDB_RUN_GROUP"
echo "[ablation] include_archived=$MAPS_INCLUDE_ARCHIVED"
echo "[ablation] openai_output=$LC_OUTPUT_VERSION"
echo "[ablation] ports=node:$MAPS_NODE_PORT mcp:$MAPS_MCP_PORT studio:$MAPS_STUDIO_PORT"

cd "$STUDIO_DIR"
if [[ "${MAPS_SKIP_ABLATION_VALIDATION:-0}" != "1" ]]; then
    python3 -m apps.maps_park.validate_ablations
fi
if [[ "${MAPS_STUDY_PREFLIGHT:-0}" == "1" ]]; then
    python3 -m apps.maps_park.validate_study_runtime
fi

# Do not kill unrelated processes. A occupied required port is a hard, explicit
# error; each ablation stack tears down its own process groups when its runner exits.
for port in "$MAPS_NODE_PORT" "$MAPS_MCP_PORT" "$MAPS_STUDIO_PORT"; do
    if (echo >"/dev/tcp/127.0.0.1/$port") >/dev/null 2>&1; then
        echo "ERROR: port $port is already in use; stop the previous MAPs stack first."
        exit 1
    fi
done

PIDS=()
cleanup() {
    status=$?
    trap - EXIT INT TERM
    for pid in "${PIDS[@]}"; do
        kill -TERM -- "-$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

start() {
    local name="$1" cwd="$2"
    shift 2
    echo "[$name] starting"
    # Python's os.setsid is available on both Linux and macOS, unlike the
    # Linux-only setsid executable. Each service remains independently
    # addressable as a process group during cleanup.
    python -c 'import os, sys; os.setsid(); os.chdir(sys.argv[1]); os.execvp(sys.argv[2], sys.argv[2:])' \
        "$cwd" "$@" >"$LOG_DIR/$name.log" 2>&1 &
    PIDS+=("$!")
}

start maps_node "$MAPS_REPO" env MAP_PORT="$MAPS_NODE_PORT" node map_backend/server.js --vis
sleep 2

MAPS_STATE_FILE="${MAPS_STATE_FILE:-$STATE_DIR/park_state.pkl}"
MCP_ARGS=(python "$MAPS_MCP_SERVER" --layout the_islands --difficulty medium --maps_port "$MAPS_NODE_PORT" --mcp_port "$MAPS_MCP_PORT" --num_parks 1 --maps_repo_dir "$MAPS_REPO" --state_file "$MAPS_STATE_FILE")
MCP_ARGS+=(--trajectory_dir "$LOG_DIR")
[[ $RESUMING -eq 1 ]] && MCP_ARGS+=(--resume)
start maps_mcp "$STUDIO_DIR" "${MCP_ARGS[@]}"
sleep 3
# The experiment needs only Neuro SAN's HTTP server. Server-only avoids spawning
# an unrelated NSFlow UI process and makes sequential teardown deterministic.
start studio "$STUDIO_DIR" python -m neuro_san_studio run --server-only --server-http-port "$MAPS_STUDIO_PORT"

registered_or_off() {
    local network="$1"
    local normalized_network
    normalized_network="$(printf '%s' "$network" | tr '[:upper:]' '[:lower:]')"
    case "$normalized_network" in
        ""|none|off|disabled) return 0 ;;
    esac
    grep -Eq "\"agent_name\"[[:space:]]*:[[:space:]]*\"$network\"" <<<"$list_json"
}

ready=0
list_json=""
for second in $(seq 1 90); do
    list_json="$(curl -m 1 -s "http://localhost:${MAPS_STUDIO_PORT}/api/v1/list" 2>/dev/null || true)"
    if registered_or_off "$MAPS_RUNNER_AGENT" \
       && registered_or_off "$MAPS_MICRO_AGENT" \
       && registered_or_off "$MAPS_MACRO_AGENT"; then
        echo "[ablation] Studio ready after ${second}s"
        ready=1
        break
    fi
    sleep 1
done

if [[ $ready -ne 1 ]]; then
    echo "ERROR: Studio did not register all required networks."
    echo "Registered response: ${list_json:-<unavailable>}"
    echo "See $LOG_DIR/studio.log"
    exit 1
fi

RUNNER_MODULE="${MAPS_RUNNER_MODULE:-apps.maps_park.ablation_runner}"
python3 -m "$RUNNER_MODULE" \
    --runner-agent "$MAPS_RUNNER_AGENT" \
    --micro-agent "$MAPS_MICRO_AGENT" \
    --macro-agent "$MAPS_MACRO_AGENT" \
    --port "$MAPS_STUDIO_PORT" \
    "${RUNNER_ARGS[@]}"
