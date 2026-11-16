# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT
"""
maps_park loop runner — two-network design with pre-validate + rollback.

Architecture (vs. the legacy single-session runner):

  ─ game-runner session ───────────────────────────────────────────────
    Network: player
    Per turn the game-runner agent picks ONE action and calls
    ProposeAction (a coded_tool that validates + persists the proposal
    to state/proposed_action.json). The runner
    reads that file, re-validates, and then commits via direct call to
    the ActionDispatcher coded tool. If pre-validate fails, the runner
    re-prompts the same session with corrective context (env untouched).

  ─ consultant sessions (two networks) ────────────────────────────────
    The old single consultant network was split in two:
      • micro  (watcher)  — mid-episode analysis.
        Invoked AFTER each step when env_step % MICRO_EVERY == 0
        (default 10), i.e. at steps 10,20,...,90 of the 100-step episode.
        Logs trials for the current episode and returns an advisory judged
        against the best-ever episode; the advisory is prepended to the next
        game-runner prompt. Every episode runs its full 100 steps.
      • macro  (planner)  — start- AND end-of-episode work.
        At episode START (fired before turn 1 of each new episode) it
        compares the best-ever episode against the last one, writes the
        episode checklist + coordinator strategy summary, and logs fresh trials.
        At episode END it promotes/resolves the episode's trials and advances it.
    The micro advisory is captured and prepended to the next game-runner
    prompt. Step 100 is done=True, so the macro end fires there, not the
    micro — the two cadences never collide.

  ─ Per-step lifecycle ────────────────────────────────────────────────
    1. Run the game-runner; read its ProposeAction proposal file.
    2. Pre-validate (env untouched); if invalid, re-prompt. After
       --max-retries failures, fall back to a wait().
    3. Dispatch the proposal once through ActionDispatcher.
    4. Keep whatever the env returns — MAPs always advances the day, and
       an action it rejects is just dropped (the day runs as a wait). So
       there is NO snapshot and NO rollback: a rejected action is logged
       as a wait and surfaced to the agent next turn.
    5. Log the post-step row, then maybe invoke the consultant.

Every turn advances the env exactly one step; we never roll back and
never replay the same step.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import logging
import os
import re
import shutil
import time
from typing import Any

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor

from coded_tools import champion_plan
from coded_tools import wandb_telemetry
from coded_tools.action_dispatcher import ActionDispatcher
from coded_tools.advance_episode import AdvanceEpisode
from coded_tools.carryover_trials import CarryoverTrials
from coded_tools.financial_metrics import financial_metrics
from coded_tools.park_status import ParkStatus
from coded_tools.promote_trial import PromoteTrial
from coded_tools.research_progress import normalize_research_progress
from coded_tools.seed_observation import SeedObservation
from coded_tools.seed_playbooks import SeedPlaybooks
from neuro_san_studio.conversation_logging import ConversationThinkingFileMessageProcessor

# The MCP SDK's streamable-HTTP client logs its handshake at INFO on every
# reconnect. Configure it before sessions are opened so runner output stays clear.
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_RUNNER_AGENT = "player"
# The consultant was split into two networks: a mid-episode micro analyzer and
# an end-of-episode macro analyzer (close-out + whole-run synthesis).
DEFAULT_MICRO_AGENT = "watcher"
DEFAULT_MACRO_AGENT = "planner"
DISABLED_AGENT_NAMES = frozenset({"", "none", "off", "disabled"})
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8090
DEFAULT_TICK_SECONDS = 5
DEFAULT_MAX_RETRIES = 25
# A close-out gets one initial attempt plus this many automatic retries.  It is
# a transaction: the game loop cannot enter the next episode until the durable
# receipt written by AdvanceEpisode matches the terminal local telemetry row.
DEFAULT_CLOSEOUT_RETRIES = 2
# Micro analyzer cadence: every 10 successful steps -> steps 10,20,...,90.
DEFAULT_MICRO_EVERY = 10

# Reward bars, passed to the micro as context and used for the champion check.
# --reward-floor is the champion bar: an episode under it is a failed strategy,
# never a fallback worth building on. Above it the champion is simply the best
# episode so far, so the bar rises on its own — champion_plan.best_reward().
DEFAULT_REWARD_FLOOR = 350000
DEFAULT_REWARD_GOAL = 5000000  # the north-star target the whole run chases


def agent_enabled(agent_name: str | None) -> bool:
    """Whether an analyzer network name denotes a real enabled network."""
    return str(agent_name or "").strip().lower() not in DISABLED_AGENT_NAMES


def reset_agent_session_cache() -> None:
    """Allow topology adapters to discard shared analyzer connections."""
    return None


# The two roots that define an experimental arm. MAPS_STATE_DIR / MAPS_LOG_DIR
# move the whole harness onto a parallel tree for the single-agent ablation, so
# the arms share neither their learned state nor their episode logs — run.ep*.jsonl
# IS the learning signal (RunTelemetry scans it for the best-ever episode), so a
# shared log dir would have each arm steering by the other's champion. The coded
# tools read the same vars via coded_tools/state_dir.py; they run in the STUDIO
# process, so run_all.sh exports both before studio boots.
_STATE_DIR = os.environ.get("MAPS_STATE_DIR", "state")
_LOG_DIR = os.environ.get("MAPS_LOG_DIR", os.path.join("logs", "maps_park"))
_USE_LAST_REWARD = os.environ.get("MAPS_USE_LAST_REWARD", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_NO_CROSS_EPISODE = os.environ.get("MAPS_NO_CROSS_EPISODE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_SKIP_MACRO_CLOSEOUT = os.environ.get("MAPS_SKIP_MACRO_CLOSEOUT", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

PROPOSAL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    _STATE_DIR,
    "proposed_action.json",
)
# Per-episode run logs: one file per episode (run.ep<NNN>.jsonl) so an
# episode is never split across files. The runner is the SOLE writer.
RUN_LOG_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        _LOG_DIR,
    )
)
TURNS_LOG_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        _LOG_DIR,
        "turns.jsonl",
    )
)

# One line per finished episode: what that episode cost in LLM spend.
# Its OWN file rather than a row in run.ep<NNN>.jsonl — several readers
# Downstream charts and park-image consumers index rows by r["step"] and
# would KeyError on a summary row that has no step.
EPISODE_COST_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        _LOG_DIR,
        "episode_cost.jsonl",
    )
)
PARK_IDS_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        _LOG_DIR,
        "park_ids.jsonl",
    )
)
LATEST_OBS_PATH = os.environ.get(
    "MAPS_LATEST_OBS_PATH",
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            _STATE_DIR,
            "latest_observations.json",
        )
    ),
)
# Agent reasoning capture. Honor the studio's THINKING_FILE / THINKING_DIR env
# vars when present; otherwise default to the standard logs/ locations so the
# runner populates the same paths the studio does (was previously a throwaway
# /tmp file with thinking_dir disabled, so no per-agent maps were ever written).
THINKING_FILE = os.environ.get(
    "THINKING_FILE",
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "logs",
            "agent_thinking.txt",
        )
    ),
)
THINKING_DIR = os.environ.get(
    "THINKING_DIR",
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "logs",
            "thinking_dir",
        )
    ),
)
# A parallel, compact transcript tree containing only HUMAN/AI turns. System
# prompts, tool traces, accounting, and duplicate framework/chat-context records
# remain available in THINKING_DIR but are not repeated in the small view.
THINKING_DIR_SMALL = os.environ.get(
    "THINKING_DIR_SMALL",
    os.path.normpath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "logs",
            "thinking-dir-small",
        )
    ),
)
# Legacy reward file retained only for arms whose planner still reads it.
LAST_REWARD_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        _STATE_DIR,
        "last_reward.md",
    )
)
CLOSEOUT_RECEIPT_PATH = os.path.normpath(AdvanceEpisode.CLOSEOUT_RECEIPT_PATH)
CLOSEOUT_PENDING_PATH = os.path.normpath(AdvanceEpisode.PENDING_PATH)

# Playbook state dir + snapshot archive. Playbooks evolve each episode, but
# only a CHAMPION is archived into state/playbook_history/<ts>_ep<NNN>_champion/
# — an episode that beat the best-so-far reward. Every other boundary (pre/post
# per episode, prerun) is noise: those playbook versions lost, so keeping them
# just buried the winners. Snapshots are append-only; nothing is ever deleted.
# MAPS_STATE_DIR moves the whole harness onto a parallel state tree (the
# single-agent ablation arm runs with state_single_agent). The coded tools read
# the same env var via coded_tools.state_dir — they live in the STUDIO process,
# so the var has to be exported before studio boots; run_all.sh does that.
PLAYBOOK_STATE_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        _STATE_DIR,
    )
)
PLAYBOOK_HISTORY_DIR = os.path.join(PLAYBOOK_STATE_DIR, "playbook_history")
# ParkStatus writes the complete planner snapshot every turn; the episode-start
# macro pass reads it before the turn-start refresh, so the runner guarantees it
# exists. The solo arm keeps its own complete status_solo snapshot.
_STATUS_BASENAME = (
    "status_solo.json"
    if os.environ.get("MAPS_MERGED_CONTEXT", "0").strip().lower() in {"1", "true", "yes", "on"}
    else "status_full.json"
)
STATUS_PATH = os.path.join(PLAYBOOK_STATE_DIR, _STATUS_BASENAME)
# save_champion_status() writes this when an episode is promoted; the episode-start
# pass READS it, so before the first promotion the runner has to seed it.
_ARM_NAME = os.environ.get("MAPS_ARM_NAME", "").strip()
_CHAMPION_STATUS_BASENAME = (
    "status_solo_champion.json"
    if _STATUS_BASENAME == "status_solo.json"
    else "status_champion.json"
    if _ARM_NAME in {"", "baseline"}
    else "status_coordinator_champion.json"
)
STATUS_CHAMPION_PATH = os.path.join(PLAYBOOK_STATE_DIR, _CHAMPION_STATUS_BASENAME)


# ── Bootstrap ────────────────────────────────────────────────────────────────


def snapshot_playbooks(tag: str, stats: dict[str, Any] | None = None) -> str | None:
    """Copy state/playbook_*.md into state/playbook_history/<ts>_<tag>/.

    Called ONLY when an episode is promoted to champion (tag ep<NNN>_champion),
    so the archive is a ladder of best-ever strategies rather than a log of every
    boundary. Append-only — never deletes. The timestamp prefix keeps every
    snapshot distinct. Returns the snapshot dir, or None if there were no
    non-empty playbooks to save.

    `stats` (the episode's verified final row) is written beside the playbooks
    as summary.json — cumulative_reward, cash and park_value — so a snapshot
    records what that playbook version actually EARNED, and versions can be
    ranked later without replaying the run.
    """
    sources = [
        p for p in sorted(glob.glob(os.path.join(PLAYBOOK_STATE_DIR, "playbook_*.md"))) if os.path.getsize(p) > 0
    ]
    if not sources:
        return None
    dest = os.path.join(PLAYBOOK_HISTORY_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}_{tag}")
    os.makedirs(dest, exist_ok=True)
    src: Any
    for src in sources:
        shutil.copy2(src, os.path.join(dest, os.path.basename(src)))
    if stats:
        summary = os.path.join(dest, "summary.json")
        with open(summary, "w", encoding="utf-8") as handle:
            json.dump(stats, handle, indent=2, default=str)
    return dest


def save_champion_status() -> None:
    """Copy the live status snapshot aside as the champion status.

    Called when an episode is promoted to champion. At that moment the status
    files still hold the park that episode FINISHED with — the runner refreshes
    them at TURN start, so nothing has overwritten them yet — so this freezes the
    best run's park. The next episode's planner reads it to compare the last
    episode's park against the best one's. Overwrites the previous champion's
    copy; a missing source is skipped (the first episodes may have none).
    """
    if _STATUS_BASENAME != "status_solo.json":
        # Freeze the explicitly complete source; the canonical baseline has no
        # separate coordinator projection.
        full = os.path.join(PLAYBOOK_STATE_DIR, "status_full.json")
        if os.path.exists(full):
            # Every structured planner using the canonical baseline instructions
            # reads status_champion. Some older ablation-specific planners still
            # read status_coordinator_champion, so non-baseline arms retain that
            # compatibility copy without changing the canonical logical name.
            targets = {
                os.path.join(PLAYBOOK_STATE_DIR, "status_champion.json"),
                os.path.join(
                    PLAYBOOK_STATE_DIR,
                    os.path.basename(STATUS_CHAMPION_PATH),
                ),
            }
            target: Any
            for target in targets:
                shutil.copy2(full, target)
        # Some ablations intentionally compare a filtered layout projection.
        # The canonical baseline reads the complete status_champion instead.
        if _ARM_NAME not in {"", "baseline"}:
            layout = os.path.join(PLAYBOOK_STATE_DIR, "status_layout.json")
            if os.path.exists(layout):
                shutil.copy2(
                    layout,
                    os.path.join(PLAYBOOK_STATE_DIR, "status_layout_champion.json"),
                )
        return

    names = ("status_solo",)
    name: Any
    for name in names:
        src = os.path.join(PLAYBOOK_STATE_DIR, f"{name}.json")
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(PLAYBOOK_STATE_DIR, f"{name}_champion.json"))


def migrate_legacy_champion_status() -> bool:
    """Rename the baseline's old champion snapshot once, preserving its contents."""
    target = os.path.join(
        PLAYBOOK_STATE_DIR,
        os.path.basename(STATUS_CHAMPION_PATH),
    )
    if os.path.basename(target) != "status_champion.json" or os.path.exists(target):
        return False
    legacy = os.path.join(PLAYBOOK_STATE_DIR, "status_coordinator_champion.json")
    if not os.path.exists(legacy):
        return False
    os.replace(legacy, target)
    return True


def ensure_canonical_champion_status() -> bool:
    """Materialize status_champion for canonical prompts in legacy ablation state.

    Older non-baseline arms froze the same complete park under
    status_coordinator_champion. Keep that compatibility file, but copy it to the
    canonical name so verbatim baseline planner instructions always resolve.
    """
    if _STATUS_BASENAME == "status_solo.json":
        return False
    canonical = os.path.join(PLAYBOOK_STATE_DIR, "status_champion.json")
    if os.path.exists(canonical):
        return False
    if os.path.exists(STATUS_CHAMPION_PATH):
        shutil.copy2(STATUS_CHAMPION_PATH, canonical)
        return True
    return False


def restore_champion_playbooks() -> str | None:
    """Copy the newest playbook_history/*_champion/ snapshot over state/playbook_*.md.

    This is the DEFAULT run mode: every run starts from the best-known playbooks
    and improves on them. Timestamped names sort chronologically, so the last one
    is the most recent champion.
    Returns the snapshot dir used, or None if no champion has ever been archived
    (first run ever — the caller then falls back to the config seeds).
    """
    latest: Any
    for latest in sorted(glob.glob(os.path.join(PLAYBOOK_HISTORY_DIR, "*_champion")), reverse=True):
        sources = glob.glob(os.path.join(latest, "playbook_*.md"))
        if sources:
            src: Any
            for src in sources:
                shutil.copy2(src, os.path.join(PLAYBOOK_STATE_DIR, os.path.basename(src)))
            return latest
    return None


def archive_state() -> str | None:
    """Clear the working state dir the --fresh way: MOVE every file into
    playbook_history/<ts>_prewipe/ rather than delete it.

    --fresh means nothing from a prior run is LOADED — champion, plan, trial
    ledgers and learned playbooks all leave the working dir — but nothing is
    destroyed: the whole prior run stays recoverable by hand in one dated dir.
    The name ends in _prewipe, not _champion, so restore_champion_playbooks()
    never picks it up.

    Two entries stay put: playbook_history/ itself, and park_state.pkl (owned by
    the MAPs env process, which run_all.sh already restarts clean without
    --resume). Returns the archive dir, or None if there was nothing to move.
    """
    keep = {"playbook_history", "park_state.pkl"}
    movable = [n for n in sorted(os.listdir(PLAYBOOK_STATE_DIR)) if n not in keep]
    if not movable:
        return None
    dest = os.path.join(PLAYBOOK_HISTORY_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}_prewipe")
    os.makedirs(dest, exist_ok=True)
    name: Any
    for name in movable:
        shutil.move(os.path.join(PLAYBOOK_STATE_DIR, name), os.path.join(dest, name))
    return dest


def strip_learned_from_seeds() -> int:
    """Drop every promoted rule from the config_files seeds — the other half of
    the --fresh contract.

    PromoteTrial mirrors each confirmed rule into the SEED as well as the working
    playbook, so wiping state alone still carries prior runs' lessons back in the
    moment SeedPlaybooks re-copies the seeds. Only lines carrying LEARNED_MARKER
    go — the same guard PromoteTrial.remove_line uses — so the hand-authored
    baseline and the section header both survive. Returns the lines dropped.
    """
    dropped = 0
    fname: Any
    for fname in sorted(set(PromoteTrial.SEED_FILES.values())):
        path = os.path.join(PromoteTrial.SEED_DIR, fname)
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.read().splitlines(keepends=True)
        except OSError:
            continue
        kept = [ln for ln in lines if PromoteTrial.LEARNED_MARKER not in ln]
        if len(kept) != len(lines):
            with open(path, "w", encoding="utf-8") as handle:
                handle.writelines(kept)
            dropped += len(lines) - len(kept)
    return dropped


def _bootstrap_env_and_plugins() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    if os.getenv("LANGFUSE_ENABLED", "").lower() in ("true", "1", "yes"):
        try:
            from neuro_san_studio.plugins.langfuse.langfuse_plugin import LangfusePlugin

            LangfusePlugin().do_initialize()
            import atexit

            from langfuse import get_client

            atexit.register(lambda: get_client().flush())
        except Exception as exc:  # noqa: BLE001
            print(f"[langfuse] init failed: {exc}")


# ── Session helpers ─────────────────────────────────────────────────────────


def open_session(agent_name: str, host: str, port: int):
    factory = AgentSessionFactory()
    session = factory.create_session(
        "http",
        agent_name,
        host,
        port,
        False,
        {"user_id": os.environ.get("USER", "maps_park")},
    )
    thread = {
        "last_chat_response": None,
        "prompt": "",
        "timeout": 5000.0,
        "num_input": 0,
        "user_input": None,
        "sly_data": None,
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
    }
    print(f"[runner] Connected to agent '{agent_name}' at {host}:{port}.")
    return session, thread


# ── Per-episode LLM spend ───────────────────────────────────────────────────
# EVERY llm call this runner makes — player turns and both consultant networks
# — goes through chat(), so accumulating there is the one hook that catches all
# of them. neuro-san already prices each call (tokens["total_cost"]), so this
# only sums; there is no pricing table to keep in step with the model.
_EPISODE_SPEND: dict[str, float] = {"cost_usd": 0.0, "tokens": 0, "llm_calls": 0, "seconds": 0.0}
_EPISODE_COST_COMPLETE = True
_EPISODE_COST_INCOMPLETE_REASON: str | None = None


def _accrue_spend(tokens: dict | None) -> None:
    """Fold one chat()'s token accounting into the current episode's total."""
    if not tokens:
        return
    _EPISODE_SPEND["cost_usd"] += float(tokens.get("total_cost") or 0.0)
    _EPISODE_SPEND["tokens"] += int(tokens.get("total_tokens") or 0)
    _EPISODE_SPEND["llm_calls"] += int(tokens.get("successful_requests") or 0)
    _EPISODE_SPEND["seconds"] += float(tokens.get("time_taken_in_seconds") or 0.0)


def _mark_episode_cost_incomplete(reason: str) -> None:
    """Flag a ledger row when this process did not observe the whole episode."""
    global _EPISODE_COST_COMPLETE, _EPISODE_COST_INCOMPLETE_REASON
    _EPISODE_COST_COMPLETE = False
    _EPISODE_COST_INCOMPLETE_REASON = reason


def write_episode_cost(episode: Any, reward: Any) -> dict:
    """Persist this episode's LLM spend and reset the tally.

    Call AFTER the close-out consult so that consult's own cost is counted.
    `cost_per_reward` is the number the whole exercise is really about: dollars
    of LLM spend per point of reward earned (None when the episode scored 0).
    The JSONL sidecar is always written, then mirrored to W&B when enabled.
    """
    reward_val = float(reward) if isinstance(reward, (int, float)) else None
    global _EPISODE_COST_COMPLETE, _EPISODE_COST_INCOMPLETE_REASON
    row = {
        "wall_time": time.time(),
        "episode": episode,
        "final_reward": reward_val,
        "cost_usd": round(_EPISODE_SPEND["cost_usd"], 4),
        # Neuro SAN derives this from its token-price table. OpenAI cached-input
        # token details are not exposed by the accounting message, so this is an
        # estimate rather than an invoice amount.
        "cost_is_estimate": True,
        "cost_complete": _EPISODE_COST_COMPLETE,
        "tokens": int(_EPISODE_SPEND["tokens"]),
        "llm_calls": int(_EPISODE_SPEND["llm_calls"]),
        "llm_seconds": round(_EPISODE_SPEND["seconds"], 1),
        "cost_per_reward": (round(_EPISODE_SPEND["cost_usd"] / reward_val, 6) if reward_val else None),
    }
    if _EPISODE_COST_INCOMPLETE_REASON:
        row["cost_incomplete_reason"] = _EPISODE_COST_INCOMPLETE_REASON
    try:
        os.makedirs(os.path.dirname(EPISODE_COST_PATH) or ".", exist_ok=True)
        with open(EPISODE_COST_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
            fh.flush()
    except OSError as exc:
        # Accounting must never take the run down with it.
        print(f"[runner] WARN: could not write episode cost: {exc}")
    if wandb_telemetry.writer_active():
        wandb_telemetry.try_log_episode_summary(row, read_episode_park_record(episode))
    _EPISODE_SPEND.update(cost_usd=0.0, tokens=0, llm_calls=0, seconds=0.0)
    _EPISODE_COST_COMPLETE = True
    _EPISODE_COST_INCOMPLETE_REASON = None
    return row


def chat(session, thread, message: str):
    os.makedirs(THINKING_DIR, exist_ok=True)
    os.makedirs(THINKING_DIR_SMALL, exist_ok=True)
    os.makedirs(os.path.dirname(THINKING_FILE) or ".", exist_ok=True)
    processor = StreamingInputProcessor("DEFAULT", THINKING_FILE, session, THINKING_DIR)
    processor.processor.add_processor(ConversationThinkingFileMessageProcessor(THINKING_FILE, THINKING_DIR_SMALL))
    thread["user_input"] = message
    thread = processor.process_once(thread)
    accounting = processor.processor.get_token_accounting()
    _accrue_spend(accounting)
    return thread.get("last_chat_response"), thread, accounting


# ── Proposal + run.jsonl I/O ────────────────────────────────────────────────


def read_proposal() -> dict | None:
    """Return the latest {proposed, validation} envelope or None if missing."""
    if not os.path.exists(PROPOSAL_PATH):
        return None
    try:
        with open(PROPOSAL_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def episode_log_path(episode: Any) -> str:
    """Path to the run log for a specific episode (run.ep<NNN>.jsonl)."""
    try:
        ep = int(episode)
    except (TypeError, ValueError):
        ep = 0
    return os.path.join(RUN_LOG_DIR, f"run.ep{ep:03d}.jsonl")


def _all_episode_logs() -> list[tuple[int, str]]:
    """All (episode_number, path) pairs present, sorted ascending by episode."""
    out: list[tuple[int, str]] = []
    path: Any
    for path in glob.glob(os.path.join(RUN_LOG_DIR, "run.ep*.jsonl")):
        match = re.search(r"run\.ep(\d+)\.jsonl$", os.path.basename(path))
        if match:
            out.append((int(match.group(1)), path))
    return sorted(out)


def latest_episode_log() -> str | None:
    """Path to the highest-numbered episode log, or None if none exist."""
    logs = _all_episode_logs()
    return logs[-1][1] if logs else None


def read_episode_park_record(episode: Any) -> dict[str, Any] | None:
    """Return the newest park-ledger row for this run-local episode."""
    try:
        wanted = int(episode)
    except (TypeError, ValueError):
        wanted = 0
    latest = None
    try:
        with open(PARK_IDS_PATH, encoding="utf-8") as fh:
            line: Any
            for line in fh:
                if not line.strip():
                    continue
                row = json.loads(line)
                run_episode = int(row.get("run_episode", row.get("episode", -1)))
                if run_episode == wanted:
                    latest = row
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return latest


def read_last_verified() -> dict | None:
    """Latest committed step from this arm's local JSONL logs."""
    path = latest_episode_log()
    last = None
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                line: Any
                for line in fh:
                    line = line.strip()
                    if line:
                        last = json.loads(line)
        except (OSError, json.JSONDecodeError):
            pass
    return last


def write_run_log_row(row: dict, episode: Any) -> None:
    os.makedirs(RUN_LOG_DIR, exist_ok=True)
    with open(episode_log_path(episode), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
        fh.flush()
    if wandb_telemetry.writer_active():
        wandb_telemetry.try_log_step(row)


def write_turn_log_record(record: dict[str, Any]) -> None:
    """Append one turn locally and mirror it to W&B when enabled."""
    os.makedirs(os.path.dirname(TURNS_LOG_PATH) or ".", exist_ok=True)
    with open(TURNS_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
        fh.flush()
    if wandb_telemetry.writer_active():
        wandb_telemetry.try_log_turn(record)


# ── Dispatch (runner-side, bypasses neuro-san agent middleware) ─────────────


def dispatch_action(proposed: dict) -> dict[str, Any]:
    """Call ActionDispatcher directly from the runner.

    Returns the raw post-step observation envelope (or {"error": ...}).
    It does NOT log anything. MAPs always advances the day and simply drops an
    action it rejects (the day runs as a wait), so there is nothing to roll
    back — the caller inspects the envelope and writes the one authoritative
    run-log row itself (env-rejected action -> logged as a wait; transport
    failure -> skipped). Keeping I/O out of here means the log is written
    exactly once, from the single place that knows the real outcome.
    """
    dispatcher = ActionDispatcher()
    args = {
        "park": "0",
        "action": proposed.get("action"),
        "args": proposed.get("args") or {},
    }
    try:
        envelope = asyncio.run(dispatcher.async_invoke(args, {}))
    except Exception as exc:  # noqa: BLE001 — surface to caller
        return {"error": f"dispatcher exception: {exc}"}
    if isinstance(envelope, dict):
        return envelope
    return {"error": "dispatcher returned non-dict", "raw": envelope}


# Park-state metrics, as opposed to the step's own outcome (reward, action,
# error). On the terminal step MAPs auto-resets, so these describe the NEW
# park and must be carried over from the previous row — see _carry_park_state.
_PARK_STATE_FIELDS = (
    "cash",
    "park_value",
    "park_rating",
    "research_speed",
    "research_progress",
    "num_rides",
    "num_shops",
    "num_staff",
    "min_uptime",
    "min_cleanliness",
    "ride_revenue",
    "shop_revenue",
    "ride_op_cost",
    "shop_op_cost",
    "staff_op_cost",
)


def _carry_park_state(row: dict, prev: dict | None) -> dict:
    """On the terminal step, keep the park as it ENDED, not as the env reset it.

    MAPs auto-resets on done, so the observation returned with done=true is a
    fresh $500 park with 0 rides. Recording that verbatim made every episode
    read as a total collapse in its final quarter (value 320k -> 500, rating
    50 -> 20), inverting every conclusion the planner/watcher drew from
    rollup.value_end / rating_end / reward_bands. reward and cumulative_reward
    are the step's OWN outcome and stay as the env reported them.
    """
    if not row.get("done") or not prev or prev.get("episode") != row.get("episode"):
        return row
    field: Any
    for field in _PARK_STATE_FIELDS:
        if prev.get(field) is not None:
            row[field] = prev[field]
    return row


def build_run_row(args: dict, envelope: dict, prev: dict | None = None) -> dict:
    """Reshape a post-step envelope into the authoritative run-log row.

    Pure transform, no I/O — the caller writes the row only once the step is
    accepted. Dropped fields (wall_time/tool/park/horizon) were redundant
    (single tool, single park, constant horizon, wall_time unused).
    `prev` is the previous row, used only to carry park state across the
    terminal step's auto-reset.
    """
    flat_args = {k: v for k, v in (args.get("args") or {}).items()}
    obs = envelope.get("observation") if isinstance(envelope.get("observation"), dict) else {}
    episode = envelope.get("episode")

    # The MAPs observation nests asset metrics under dict groups (not flat
    # num_* keys), names cash/value as "money"/"value", and reports
    # reward/cumulative_reward on the envelope (0.0 is a valid value, so
    # coalesce on None, never with `or`).
    rides = obs.get("rides") if isinstance(obs.get("rides"), dict) else {}
    shops = obs.get("shops") if isinstance(obs.get("shops"), dict) else {}
    staff = obs.get("staff") if isinstance(obs.get("staff"), dict) else {}
    finances = financial_metrics(envelope, obs)

    def first_set(*values: Any) -> Any:
        value: Any
        for value in values:
            if value is not None:
                return value
        return None

    row = {
        "action": args.get("action"),
        "episode": episode,
        "step": first_set(envelope.get("step"), obs.get("step")),
        "cash": obs.get("money"),
        "park_value": obs.get("value"),
        "park_rating": obs.get("park_rating"),
        "research_speed": obs.get("research_speed"),
        "research_progress": normalize_research_progress(obs.get("research_progress"), obs.get("research_speed")),
        "cumulative_reward": first_set(envelope.get("cumulative_reward"), obs.get("cumulative_reward")),
        "reward": first_set(envelope.get("reward"), obs.get("reward")),
        "done": bool(envelope.get("done")),
        "error": envelope.get("error"),
        "num_rides": rides.get("total_rides"),
        "num_shops": shops.get("total_shops"),
        "num_staff": len(staff.get("staff_list") or []),
        "min_uptime": rides.get("min_uptime"),
        "min_cleanliness": obs.get("min_cleanliness"),
        "ride_revenue": rides.get("total_revenue_generated"),
        "shop_revenue": shops.get("total_revenue_generated"),
        "ride_op_cost": rides.get("total_operating_cost"),
        "shop_op_cost": shops.get("total_operating_cost"),
        "staff_op_cost": staff.get("total_operating_cost"),
        **finances,
        # research_speed is a park-state metric sourced from obs above; exclude it
        # from the proposal spread so FinanceGate's per-proposal None (set for every
        # non-set_research action) can't clobber the real observed research speed.
        **{
            k: v
            for k, v in flat_args.items()
            if k
            not in {
                "park",
                "action",
                "args",
                "research_speed",
                "asset_investment",
                "daily_profit",
            }
        },
    }
    return _carry_park_state(row, prev)


# ── Consultant invocation ──────────────────────────────────────────────────


def consult(
    session, thread, kind: str, verified: dict | None, label: str = "consultant", extra: str = ""
) -> str | None:
    """Invoke a consultant network (micro or macro); return its advisory (or None).

    `label` is purely cosmetic (which network is being called) for the logs;
    the agent routes on `kind` (periodic -> micro; episode_start / episode_end
    -> macro). `extra` is appended verbatim to the message (e.g. the reward
    floor/goal on periodic).
    """
    ep = verified.get("episode") if verified else None
    step = verified.get("step") if verified else None
    cum = verified.get("cumulative_reward") if verified else None
    final = verified.get("cumulative_reward") if (verified and verified.get("done")) else None
    msg = f"kind={kind} episode={ep} step={step} cumulative_reward={cum} final_reward={final}"
    if extra:
        msg += " " + extra
    print(f"[{label}] invoking ({kind}) at episode={ep} step={step}")
    response, _thread, tokens = chat(session, thread, msg)
    if tokens:
        print(f"[{label} tokens] total={tokens.get('total_tokens')} cost={tokens.get('total_cost')}")
    return (response or "").strip() or None


def closeout_committed(verified: dict | None) -> bool:
    """Whether AdvanceEpisode committed this exact terminal telemetry row."""
    if not verified or not verified.get("done"):
        return False
    try:
        with open(CLOSEOUT_RECEIPT_PATH, encoding="utf-8") as handle:
            receipt = json.load(handle)
        return int(receipt.get("episode")) == int(verified.get("episode")) and float(
            receipt.get("final_reward")
        ) == float(verified.get("cumulative_reward"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False


def close_episode_with_retry(
    session,
    thread,
    verified: dict,
    *,
    max_retries: int = DEFAULT_CLOSEOUT_RETRIES,
    label: str = "macro",
) -> str | None:
    """Run close-out until its durable receipt commits, or stop the runner.

    The receipt, not the model's prose and not W&B, is authoritative.  Every
    attempt re-reads local episode telemetry through the planner's normal tools.
    Mutating close-out tools are idempotent, so a retry safely finishes a pass
    that promoted some rules before a later tool failed.
    """
    if not verified.get("done"):
        raise RuntimeError("close-out requires a terminal local telemetry row")
    episode = verified.get("episode")
    reward = verified.get("cumulative_reward")
    if episode is None or reward is None:
        raise RuntimeError("close-out terminal row is missing episode or cumulative_reward")
    recovery_error = AdvanceEpisode.recover_pending()
    if recovery_error is not None:
        raise RuntimeError(recovery_error)
    if closeout_committed(verified):
        print(f"[{label}] close-out ep{episode} already committed; no retry needed.")
        return None

    retries = max(0, int(max_retries))
    attempts = retries + 1
    failures: list[str] = []
    response: str | None = None
    for attempt in range(1, attempts + 1):
        recovery_error = AdvanceEpisode.recover_pending()
        if recovery_error is not None:
            failures.append(recovery_error)
            break
        retry_note = (
            "retry=false" if attempt == 1 else "retry=true previous_attempt_did_not_write_the_closeout_receipt"
        )
        extra = (
            f"closeout_attempt={attempt}/{attempts} {retry_note} "
            "authoritative_source=local_episode_telemetry "
            "repeat_unfinished_closeout_steps; mutations_are_idempotent; "
            "wandb_is_optional_reporting_only"
        )
        try:
            response = consult(session, thread, "episode_end", verified, label=label, extra=extra)
            failure = response or "no advisory returned"
        except Exception as exc:  # noqa: BLE001 — retries include transport failures
            failure = f"{type(exc).__name__}: {exc}"

        explicit_error = bool(response and response.lstrip().upper().startswith("ERROR:"))
        if closeout_committed(verified) and not explicit_error:
            if attempt > 1:
                print(f"[{label}] close-out ep{episode} committed on retry {attempt - 1}/{retries}.")
            return response

        failures.append(failure)
        if attempt < attempts:
            preview = failure.replace("\n", " ")[:240]
            print(
                f"[{label}] WARN close-out ep{episode} attempt {attempt} did not "
                f"commit ({preview}); retrying from local telemetry."
            )

    detail = failures[-1].replace("\n", " ")[:500] if failures else "unknown failure"
    raise RuntimeError(
        f"close-out ep{episode} failed to commit after {attempts} attempt(s): {detail}. "
        "Runner stopped before advancing to the next episode."
    )


# ── One-shot consult mode ────────────────────────────────────────────────────


def run_consult_only(args) -> None:
    """Invoke a single analyzer network once against the latest episode log.

    Runs NO game loop and performs none of the runner's fresh-start resets, so
    playbooks/state are left exactly as the cancelled run left them. Assumes the
    studio server + MAPs env are already up (e.g. booted by run_macro.sh).

    For 'macro' the message uses kind=episode_end, which drives the network's
    full close-out (promote/resolve trials + advance_episode). The latest run.ep*.jsonl is
    read as context even when its last row has done=false (a cancelled episode).
    """
    kind = "episode_end" if args.consult_only == "macro" else "periodic"
    agent_name = args.macro_agent if args.consult_only == "macro" else args.micro_agent

    # This path skips normal startup seeding, so ensure trial-ledger files exist
    # without clobbering the cancelled run.
    seed = SeedPlaybooks().invoke({"overwrite": False}, {})
    if seed.get("trial_ledgers_created"):
        print(f"[runner] Initialized missing trial ledgers: {seed['trial_ledgers_created']}")
    if seed.get("errors"):
        print(f"[runner] WARN seed errors: {seed['errors']}")

    try:
        session, thread = open_session(agent_name, args.host, args.port)
    except Exception as exc:  # noqa: BLE001
        print(f"[runner] Could not connect to '{agent_name}' at {args.host}:{args.port}: {exc}")
        print("[runner] Is the studio server up? Boot the backend with apps/maps_park/run_macro.sh.")
        return
    verified = read_last_verified()
    if verified is None:
        print("[runner] WARN: no episode telemetry found; invoking with empty context.")
    else:
        print(
            f"[runner] consult-only ({args.consult_only}) against "
            f"episode={verified.get('episode')} step={verified.get('step')} "
            f"done={verified.get('done')}"
        )
    if kind == "episode_end" and verified and verified.get("done"):
        advisory = close_episode_with_retry(
            session,
            thread,
            verified,
            max_retries=args.closeout_retries,
            label=args.consult_only,
        )
    else:
        advisory = consult(session, thread, kind, verified, label=args.consult_only)
    print("\n======================================================================")
    print(f"[{args.consult_only}] advisory:\n")
    print(advisory or "(no advisory returned)")


# ── Main loop ──────────────────────────────────────────────────────────────


def main():
    _bootstrap_env_and_plugins()

    parser = argparse.ArgumentParser(description="maps_park loop runner")
    parser.add_argument("--runner-agent", default=DEFAULT_RUNNER_AGENT)
    parser.add_argument(
        "--micro-agent", default=DEFAULT_MICRO_AGENT, help="Mid-episode (kind=periodic) analyzer network."
    )
    parser.add_argument(
        "--macro-agent",
        default=DEFAULT_MACRO_AGENT,
        help="End-of-episode (kind=episode_end) close-out + whole-run analyzer network.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--tick", type=float, default=DEFAULT_TICK_SECONDS, help="Seconds between turns. 0 = no delay."
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Max pre/post validation retries before restoring the env and re-trying the same step on the next tick.",
    )
    parser.add_argument(
        "--closeout-retries",
        type=int,
        default=DEFAULT_CLOSEOUT_RETRIES,
        help="Automatic retries after a failed episode close-out "
        "(default 2; the runner will not advance without a "
        "matching local close-out receipt).",
    )
    parser.add_argument(
        "--micro-every",
        type=int,
        default=DEFAULT_MICRO_EVERY,
        help="Invoke the micro analyzer after every N successful steps (default 10 -> steps 10,20,...,90).",
    )
    parser.add_argument(
        "--reward-floor",
        type=int,
        default=DEFAULT_REWARD_FLOOR,
        help="Champion bar (default 350000): an episode below it "
        "never becomes champion. Also passed to the micro as the "
        "floor it judges the run against, raised to the best-ever "
        "episode's reward once one lands.",
    )
    parser.add_argument(
        "--reward-goal",
        type=int,
        default=DEFAULT_REWARD_GOAL,
        help="North-star cum_reward target for the run; passed to the micro for context.",
    )
    parser.add_argument(
        "--consult-only",
        choices=("macro", "micro"),
        nargs="?",
        const="macro",
        default=None,
        help="Run NO game loop: invoke one analyzer network a single "
        "time against the latest episode telemetry, print its advisory, "
        "and exit. Bare --consult-only defaults to 'macro', which "
        "fires the full episode-end close-out (cross-run analysis + "
        "promote/resolve trials + advance_episode) — same side "
        "effects as a normal episode end. Pass 'micro' for the "
        "mid-episode analyzer instead. Use apps/maps_park/run_macro.sh "
        "to boot the backend (in --resume mode) and run this in one step.",
    )
    # Three run modes. Default (neither flag) starts from the best-known
    # champion; the two flags are the escapes at either end of that.
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--resume",
        action="store_true",
        help="Continue the in-flight run as is: keep every state file, "
        "including state/playbook_*.md, so learned edits survive.",
    )
    mode.add_argument(
        "--fresh",
        action="store_true",
        help="Start from nothing: MOVE every state file (playbooks, trial "
        "ledgers, champion plan and reward) into "
        "playbook_history/<ts>_prewipe/ and reset the playbooks to their "
        "config_files seeds. Nothing is deleted; nothing from a prior run "
        "is loaded — not even the best episode in the playbook_history "
        "archive.",
    )
    args = parser.parse_args()

    # One-shot analyzer mode: invoke a single network and exit, running none of
    # the game loop or fresh-start resets below (playbooks/state untouched).
    if args.consult_only:
        run_consult_only(args)
        return

    if not args.resume:
        # Clear stale observation cache so each fresh run starts clean.
        if os.path.exists(LATEST_OBS_PATH):
            os.remove(LATEST_OBS_PATH)
            print(f"[runner] Cleared stale observation cache: {LATEST_OBS_PATH}")

        # Clear stale proposal file too.
        if os.path.exists(PROPOSAL_PATH):
            os.remove(PROPOSAL_PATH)

    runner_session, runner_thread = open_session(args.runner_agent, args.host, args.port)
    # Two analyzer sessions: micro (mid-episode) and macro (episode-end). Each
    # gets its own session/thread so their conversation histories never mix.
    micro_session, micro_thread = (None, None)
    macro_session, macro_thread = (None, None)
    if agent_enabled(args.micro_agent):
        try:
            micro_session, micro_thread = open_session(args.micro_agent, args.host, args.port)
        except Exception as exc:  # noqa: BLE001
            print(f"[runner] micro analyzer session failed ({exc}); running without it.")
            micro_session = None
    else:
        print("[runner] micro analyzer OFF.")
    if agent_enabled(args.macro_agent):
        try:
            macro_session, macro_thread = open_session(args.macro_agent, args.host, args.port)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                f"macro analyzer '{args.macro_agent}' is required for transactional "
                f"close-out but its session failed: {exc}"
            ) from exc
    else:
        print("[runner] macro analyzer OFF.")

    advisory_for_next_turn: str | None = None
    # Kept SEPARATE from advisory_for_next_turn: a rejected action and a watcher
    # advisory can both land on the same step (10, 20, ... 90), and sharing one slot
    # meant the consult() result silently clobbered the rejection every time.
    feedback_for_next_turn: str | None = None
    user_input = "Start the run. Take one action on park 0."
    turn = 0

    # Startup seed: lay down the seven playbooks before the first turn via the
    # SeedPlaybooks coded tool (deterministic file copy, no LLM). Which base they
    # start from is the whole difference between the three run modes:
    #   --fresh    move the whole state dir into the archive, reset to the seeds.
    #   --resume   keep the working copies — an in-flight run continues untouched.
    #   (default)  restore the newest champion snapshot and improve on THAT, so a
    #              run never regresses to the seeds. The champion plan + reward on
    #              disk survive too, so restore_last_good() below re-applies the
    #              best-known plan.
    if args.fresh:
        archived = archive_state()
        print(
            f"[runner] --fresh: moved the prior run's state to {archived} — nothing deleted, nothing carried in."
            if archived
            else "[runner] --fresh: state dir already empty."
        )
        print(
            f"[runner] --fresh: dropped {strip_learned_from_seeds()} promoted rule(s) "
            f"from the config seeds (the archived copies still carry them)."
        )
        overwrite = True
    elif args.resume:
        overwrite = False
    else:
        champion = restore_champion_playbooks()
        if champion:
            print(f"[runner] Restored champion playbooks from {champion}; this run improves on them.")
        else:
            print("[runner] No champion archived yet — starting from the config_files seeds.")
        overwrite = champion is None
    seed_result = SeedPlaybooks().invoke({"overwrite": overwrite}, {})
    print(
        f"[runner] Playbooks seeded={seed_result['seeded']} "
        f"skipped={seed_result['skipped']} errors={seed_result['errors']}"
    )

    # The canonical baseline no longer consumes the legacy reward file. Remove a
    # stale copy even on resume; Solo and other opted-in arms retain it.
    if not _USE_LAST_REWARD:
        try:
            os.remove(LAST_REWARD_PATH)
            print(f"[runner] Removed legacy {os.path.basename(LAST_REWARD_PATH)}")
        except FileNotFoundError:
            pass

    if not args.resume:
        if _USE_LAST_REWARD:
            with open(LAST_REWARD_PATH, "w", encoding="utf-8") as fh:
                fh.write("cumulative_reward: 0\n")
            print(f"[runner] New run: reset {os.path.basename(LAST_REWARD_PATH)} to 0")
        # Episode numbers restart at zero for a new run.  A receipt from the
        # previous run could otherwise falsely commit ep0 when rewards coincide.
        for closeout_path in (CLOSEOUT_RECEIPT_PATH, CLOSEOUT_PENDING_PATH):
            try:
                os.remove(closeout_path)
            except FileNotFoundError:
                pass
        print("[runner] New run: cleared prior close-out receipt")

    existing_wandb_path = wandb_telemetry.current_run_path()
    wandb_telemetry.try_initialize_run(
        resume=args.resume,
        config={
            "runner_agent": args.runner_agent,
            "micro_agent": args.micro_agent,
            "macro_agent": args.macro_agent,
            "micro_every": args.micro_every,
            "reward_floor": args.reward_floor,
            "reward_goal": args.reward_goal,
            "episode_limit": os.environ.get("MAPS_EPISODE_LIMIT"),
            "state_dir": _STATE_DIR,
            "ablation_arm": os.environ.get("MAPS_ABLATION_ARM"),
            "study_id": os.environ.get("MAPS_STUDY_ID"),
            "topology": os.environ.get("MAPS_TOPOLOGY"),
            "self_improvement": os.environ.get("MAPS_SELF_IMPROVEMENT"),
            "cross_episode_carryover": not _NO_CROSS_EPISODE,
            "macro_closeout": not _SKIP_MACRO_CLOSEOUT,
            "model_provider": os.environ.get("MAPS_MODEL_PROVIDER"),
            "player_model": os.environ.get("MAPS_PLAYER_MODEL"),
            "planner_model": os.environ.get("MAPS_PLANNER_MODEL"),
            "watcher_model": os.environ.get("MAPS_WATCHER_MODEL"),
            "model_context_tokens": os.environ.get("MAPS_MODEL_CONTEXT_TOKENS"),
        },
    )
    if args.resume and wandb_telemetry.writer_active() and not existing_wandb_path:
        wandb_telemetry.try_migrate_legacy_jsonl(RUN_LOG_DIR, EPISODE_COST_PATH, TURNS_LOG_PATH)

    prev_episode_done = False
    # Episode number for the upcoming episode's start-of-episode macro pass.
    # turn 1 is episode 0; bumped to ended_episode+1 when an episode finishes.
    next_episode_num = 0
    # --resume onto a killed run: the counter above is a fresh-process 0, but the
    # env is wherever the dead process left it. Read the ground truth off disk.
    # done=true means that episode FINISHED and its close-out never ran (the kill
    # landed between the last step and the macro pass), so we are starting the
    # NEXT episode, not continuing the old one.
    resume_mid_episode = False
    if args.resume:
        last_verified = read_last_verified() or {}
        ep_on_disk = last_verified.get("episode") or 0
        if last_verified and not last_verified.get("done"):
            next_episode_num = ep_on_disk
            resume_mid_episode = True
            _mark_episode_cost_incomplete(
                f"process resumed episode {ep_on_disk} after step "
                f"{last_verified.get('step')}; pre-restart LLM spend is unavailable"
            )
            print(
                f"[runner] --resume: continuing in-flight ep{ep_on_disk} "
                f"(step {last_verified.get('step')}) — no start pass."
            )
        elif last_verified:
            next_episode_num = ep_on_disk + 1
            if not closeout_committed(last_verified):
                print(
                    f"[runner] --resume: ep{ep_on_disk} reached the boundary without "
                    "a close-out receipt; retrying the full close-out before "
                    f"ep{next_episode_num}."
                )
                if macro_session is not None and not _SKIP_MACRO_CLOSEOUT:
                    close_episode_with_retry(
                        macro_session,
                        macro_thread,
                        last_verified,
                        max_retries=args.closeout_retries,
                        label="macro-resume",
                    )
                else:
                    result = AdvanceEpisode().invoke(
                        {
                            "final_reward": last_verified.get("cumulative_reward"),
                            "episode": ep_on_disk,
                        },
                        {},
                    )
                    if isinstance(result, str) and result.startswith("ERROR:"):
                        raise RuntimeError(result)
            else:
                print(
                    f"[runner] --resume: ep{ep_on_disk} close-out receipt is already "
                    f"committed; starting ep{next_episode_num}."
                )

            # Token spend before the restart is unrecoverable, so no cost row is
            # fabricated here.  Strategy learning is recoverable because the
            # close-out re-reads authoritative local telemetry above.
            ep_cum = last_verified.get("cumulative_reward")
            if ep_cum is not None:
                if champion_plan.promote_plan(ep_cum, args.reward_floor):
                    save_champion_status()
                    print(f"[runner] Recovered close-out: ep{ep_on_disk} (reward={ep_cum}) is the new champion.")
                else:
                    print(
                        f"[runner] Recovered close-out: ep{ep_on_disk} reward={ep_cum} "
                        f"booked as the baseline; champion unchanged."
                    )

    try:
        while True:
            turn += 1
            print(f"\n========== TURN {turn} ==========")

            # The runner authoritatively knows when an episode is fresh: the
            # process just started (turn 1) or the prior turn ended an episode.
            # The preflight custodian consumes this explicit mode instead of
            # re-inferring "fresh" from step==1.
            preflight_mode = "fresh_episode" if (turn == 1 or prev_episode_done) else "continue"

            # If the previous turn ended an episode, ensure the new episode's
            # playbooks exist before the game-runner acts. overwrite=False:
            # learned edits promoted at the prior episode's close survive.
            if prev_episode_done:
                roll = SeedPlaybooks().invoke({"overwrite": False}, {})
                if roll["seeded"]:
                    print(f"[runner] New-episode playbooks created: {roll['seeded']}")
                prev_episode_done = False

            # Start-of-episode MACRO pass: compare prior results, write the plan,
            # and log fresh trials BEFORE park_director acts on turn 1. Skipped only when
            # resuming an episode that is genuinely still in flight; a --resume
            # that lands on a NEW episode gets the full pass, or it would play 100
            # turns on the dead process's plan.
            if (
                preflight_mode == "fresh_episode"
                and macro_session is not None
                and not (turn == 1 and resume_mid_episode)
            ):
                # Restore the champion plan as the BASE for EVERY episode start
                # (deterministic, no LLM), then run the macro to REFINE it — so the
                # macro always starts from the best-known strategy, not the last
                # (possibly worse) run. restore_last_good() is a no-op (returns False)
                # when there is no champion yet, so the first episode plans from
                # telemetry.
                if champion_plan.restore_last_good():
                    print(f"[runner] Restored champion as the base for ep{next_episode_num}; macro will refine it.")
                # Both macro passes read status_full (episode_end for the park THIS
                # episode finished with), and both stop on any tool
                # error. On the FIRST episode of a run there is no prior episode and
                # (after --fresh) archive_state() has moved those files out, while the
                # turn-start ParkStatus below has not run yet — so the read fails and
                # the pass aborts before it logs trials or writes the plan.
                # Seed them once so the files always exist: this writes the empty
                # starting park, the honest answer when there is nothing to review.
                # From episode 1 on they already hold last episode's final park and
                # this is a no-op — deliberately NOT refreshed, or the macro would
                # review the post-reset empty park instead of the run it is supposed
                # to learn from.
                if not os.path.exists(STATUS_PATH):
                    SeedObservation().invoke({"park": 0}, {})
                    asyncio.run(ParkStatus().async_invoke({"park": "0"}, {}))
                    print(f"[runner] Seeded {STATUS_PATH} for the episode-start pass (no prior episode to review).")
                # episode_start reads the champion status, which only exists once an
                # episode has been promoted — so before the first champion the read
                # would error the whole pass. Seed it from the live status (the empty
                # starting park on a fresh run, last episode's park mid-run); the first
                # promotion overwrites it with the real champion's park. Existing
                # baselines retain their champion through the one-time filename rename.
                if not os.path.exists(STATUS_CHAMPION_PATH):
                    if migrate_legacy_champion_status():
                        print("[runner] Renamed the legacy champion status to status_champion.json.")
                    else:
                        save_champion_status()
                        print("[runner] Seeded champion status for the episode-start pass (no champion promoted yet).")
                if ensure_canonical_champion_status():
                    print(
                        "[runner] Copied the legacy ablation champion status to "
                        "status_champion.json for the canonical planner prompt."
                    )
                start_ctx = {"episode": next_episode_num, "step": 0, "cumulative_reward": 0, "done": False}
                consult(macro_session, macro_thread, "episode_start", start_ctx, label="macro-start")

            if preflight_mode == "fresh_episode":
                swept = CarryoverTrials().invoke({"episode": next_episode_num}, {})
                cleared = swept.get("cleared") if isinstance(swept, dict) else None
                if cleared:
                    print(
                        f"[runner] Retired {len(cleared)} stale trial(s) from earlier "
                        f"episodes before ep{next_episode_num}: {', '.join(cleared)}"
                    )

            # Seed turn-1's observation deterministically (moved out of park_director's
            # instructions): world_observe caches the park's current state WITHOUT
            # stepping, so the first ParkStatus returns real state instead of "No
            # observation stored yet" — no throwaway wait. On --resume this just
            # re-caches the in-flight state (world_observe returns current, not step 0).
            if preflight_mode == "fresh_episode":
                seeded = SeedObservation().invoke({"park": 0}, {})
                print(f"[runner] Seeded fresh-episode observation: {seeded}")

            # Refresh status_full and every specialist slice from the latest observation
            # BEFORE the coordinator + specialists read them. Deterministic (no decision),
            # so the runner owns it (like SeedObservation); the baseline coordinator and
            # watcher both read the complete status_full snapshot.
            park_snapshot = asyncio.run(ParkStatus().async_invoke({"park": "0"}, {}))
            if isinstance(park_snapshot, dict) and park_snapshot.get("error"):
                print(f"[runner] ParkStatus warning: {park_snapshot['error']}")
            # Rare (e.g. --resume onto a finished episode): nothing to act on — end the run.
            # (This replaces park_director's turn-start done-check.)
            if isinstance(park_snapshot, dict) and park_snapshot.get("done"):
                print(
                    f"[runner] Park already done at turn start "
                    f"(final_reward={park_snapshot.get('cumulative_reward')}); ending run."
                )
                break

            verified_before = read_last_verified()

            prompt = f"[PREFLIGHT MODE] {preflight_mode}\n\n" + user_input
            if advisory_for_next_turn:
                prompt = f"[consultant advisory]\n{advisory_for_next_turn}\n[/consultant advisory]\n\n" + prompt
                advisory_for_next_turn = None
            if feedback_for_next_turn:
                prompt = feedback_for_next_turn + "\n\n" + prompt
                feedback_for_next_turn = None
            turn_done = False
            last_proposed: dict = {}
            verified_after: dict | None = verified_before
            tokens: dict = {}
            proposal_ok = False

            # Ask the agent for a VALID proposal. Pre-validation does not touch
            # the env, so re-prompting on rejection is cheap and safe — there is
            # no snapshot and no rollback anywhere in this loop.
            attempt: Any
            for attempt in range(1, args.max_retries + 1):
                # Clear the proposal file so we know the agent wrote a fresh one.
                if os.path.exists(PROPOSAL_PATH):
                    os.remove(PROPOSAL_PATH)

                response, runner_thread, tokens = chat(runner_session, runner_thread, prompt)
                print(f"[runner reply attempt={attempt}] " + (response or "(no response)"))

                proposal_envelope = read_proposal()
                # ponytail: retries go to park_director, which cannot call
                # ProposeAction itself (that's strategy_coordinator's tool) and
                # requires the [PREFLIGHT MODE] header. Keep the header and phrase
                # the fix in the director's own terms, or it spins to max_retries.
                if proposal_envelope is None:
                    prompt = (
                        f"[PREFLIGHT MODE] {preflight_mode}\n\n"
                        "ERROR: no action was proposed this turn. Re-run your per-turn "
                        "sequence and call strategy_coordinator, which must propose "
                        "exactly one action via ProposeAction."
                    )
                    continue

                last_proposed = proposal_envelope.get("proposed", {}) or {}
                validation = proposal_envelope.get("validation", {})
                if validation.get("ok"):
                    proposal_ok = True
                    break
                reasons = validation.get("reasons") or ["ProposeAction reported ok=false"]
                print(f"[runner] ProposeAction rejected: {reasons}")
                prompt = (
                    f"[PREFLIGHT MODE] {preflight_mode}\n\n"
                    f"ERROR: the proposed action was rejected. Reasons: {reasons}. "
                    f"The env was NOT touched. Call strategy_coordinator again to "
                    f"propose a different concrete action."
                )

            # If the agent never produced a valid proposal, advance the day with
            # a wait() instead of getting stuck or rolling anything back.
            if not proposal_ok:
                print(f"[runner] No valid proposal after {args.max_retries} attempts; advancing the day with wait().")
                last_proposed = {"park": 0, "action": "wait", "args": {}}

            # Dispatch exactly once and KEEP whatever the env returns. MAPs always
            # advances the day; an action the env rejects is simply dropped and the
            # day runs as a wait. So there is nothing to roll back — we record the
            # real post-step state and move on. A rejected action is logged as a
            # wait (the park did not change) with the rejection noted, and surfaced
            # to the agent next turn so it can pick something valid.
            dispatch_envelope = dispatch_action(last_proposed)
            if dispatch_envelope.get("step") is None and dispatch_envelope.get("error"):
                # Transport/dispatcher failure: the day did NOT advance. Skip
                # logging a phantom step and try again next tick.
                print(f"[runner] DISPATCH failed (day did not advance): {dispatch_envelope['error']}")
            else:
                candidate = build_run_row(last_proposed, dispatch_envelope, verified_before)
                env_err = candidate.get("error")
                if env_err:
                    candidate["rejected_action"] = candidate.get("action")
                    candidate["action"] = "wait"
                    k: Any
                    for k in ("type", "subtype", "subclass", "price", "x", "y", "order_quantity"):
                        candidate.pop(k, None)
                write_run_log_row(candidate, candidate.get("episode"))
                verified_after = candidate
                turn_done = True
                status = "OK" if not env_err else f"REJECTED-by-env, counted as wait: {env_err}"
                print(
                    f"[verified] step={candidate.get('step')}/100  "
                    f"action={candidate.get('action')}  "
                    f"cash=${candidate.get('cash')}  "
                    f"asset_investment=${candidate.get('asset_investment')}  "
                    f"daily_profit=${candidate.get('daily_profit')}  "
                    f"reward={candidate.get('reward')}  "
                    f"cum={candidate.get('cumulative_reward')}  {status}"
                    + ("  EPISODE DONE" if candidate.get("done") else "")
                )
                if env_err:
                    # Literal "feedback:" — strategy_coordinator's step 2 keys on
                    # that token to route the cause back to the owning specialist.
                    feedback_for_next_turn = (
                        f"feedback: your previous action ({candidate.get('rejected_action')}) was "
                        f"rejected by the env: {env_err}. It counted as a wait — pick a valid action."
                    )

            # Per-turn ledger row (sidecar for replay, not the env's run.jsonl).
            turn_record = {
                "wall_time": time.time(),
                "turn": turn,
                "attempts": attempt,
                "turn_done": turn_done,
                "proposed": last_proposed,
                "verified_after": verified_after,
                "tokens": tokens,
            }
            write_turn_log_record(turn_record)

            # Analyzer cadence. On the done=true row -> macro network (episode
            # close-out + whole-run analysis). Otherwise, every N successful
            # steps (10,20,...,90) -> micro network (mid-episode analysis).
            # Step 100 is done=true, so macro wins there and the two never
            # collide. Each fires only if its session opened.
            if turn_done and verified_after:
                step_n = verified_after.get("step") or 0
                episode_done = bool(verified_after.get("done"))
                if episode_done:
                    if macro_session is not None and not _SKIP_MACRO_CLOSEOUT:
                        advisory_for_next_turn = close_episode_with_retry(
                            macro_session,
                            macro_thread,
                            verified_after,
                            max_retries=args.closeout_retries,
                            label="macro",
                        )
                    elif _SKIP_MACRO_CLOSEOUT:
                        advance_result = AdvanceEpisode().invoke(
                            {
                                "final_reward": verified_after.get("cumulative_reward"),
                                "episode": verified_after.get("episode"),
                            },
                            {},
                        )
                        if isinstance(advance_result, str) and advance_result.startswith("ERROR:"):
                            raise RuntimeError(advance_result)
                        print("[runner] Skipped planner close-out; committed deterministic episode boundary.")
                    ended_ep = verified_after.get("episode") or 0
                    # After the close-out consult, so its cost lands in THIS
                    # episode's total rather than leaking into the next one.
                    spend = write_episode_cost(ended_ep, verified_after.get("cumulative_reward"))
                    print(
                        f"[cost] episode {ended_ep}: ${spend['cost_usd']:.2f}  "
                        f"{spend['tokens']:,} tokens  {spend['llm_calls']} calls"
                        + (f"  ${spend['cost_per_reward']:.6f}/reward" if spend["cost_per_reward"] else "")
                    )
                    if _NO_CROSS_EPISODE:
                        # The boundary reset has restored seed policy and hidden
                        # prior telemetry. New sessions also remove chat history
                        # as a covert cross-episode learning channel.
                        advisory_for_next_turn = None
                        reset_agent_session_cache()
                        runner_session, runner_thread = open_session(args.runner_agent, args.host, args.port)
                        if agent_enabled(args.micro_agent):
                            micro_session, micro_thread = open_session(args.micro_agent, args.host, args.port)
                        if agent_enabled(args.macro_agent):
                            macro_session, macro_thread = open_session(args.macro_agent, args.host, args.port)
                        print("[runner] Opened fresh player/planner/watcher sessions for the next episode.")
                    prev_episode_done = True
                    # A rejection on the final step describes a park that no longer
                    # exists; don't carry it into the fresh episode's turn 1.
                    feedback_for_next_turn = None
                    # Next loop iteration is a fresh episode; its start pass
                    # plans episode (ended_episode + 1).
                    next_episode_num = (verified_after.get("episode") or 0) + 1
                    # Champion checkpoint (deterministic): an episode promotes its
                    # plan to champion ONLY if it beats the best-so-far reward.
                    ep_reward = verified_after.get("cumulative_reward")
                    if champion_plan.promote_plan(ep_reward, args.reward_floor):
                        print(
                            f"[runner] New best episode (reward={ep_reward}) — promoted "
                            f"plan to champion; the bar now rises to it."
                        )
                        # Freeze this episode's finished park beside the plan, so the
                        # next episode_start can read the BEST run's park, not just
                        # the last run's.
                        save_champion_status()
                        # ONLY a champion is archived. The playbooks on disk right
                        # now are the ones that earned ep_reward (the close-out's
                        # promotions already landed above), so this snapshot IS the
                        # winning strategy — history holds best-ever versions only,
                        # not one dir per episode boundary.
                        snap = snapshot_playbooks(f"ep{ended_ep:03d}_champion", verified_after)
                        if snap:
                            print(
                                f"[runner] Archived champion playbooks to {snap} "
                                f"(reward={ep_reward} cash={verified_after.get('cash')} "
                                f"park_value={verified_after.get('park_value')})"
                            )
                elif (
                    micro_session is not None
                    and args.micro_every > 0
                    and step_n > 0
                    and step_n % args.micro_every == 0
                ):
                    # Floor rises to the best-ever episode: 0 until the first one
                    # lands, then the champion's reward. --reward-floor is a hard
                    # minimum it never drops below.
                    floor_now = max(args.reward_floor, champion_plan.best_reward())
                    advisory_for_next_turn = consult(
                        micro_session,
                        micro_thread,
                        "periodic",
                        verified_after,
                        label="micro",
                        extra=f"floor={floor_now:.0f} goal={args.reward_goal}",
                    )

            user_input = "Take one action on park 0."
            if args.tick > 0:
                time.sleep(args.tick)
    except KeyboardInterrupt:
        print("\n[runner] Interrupted; exiting.")
    finally:
        wandb_telemetry.try_finish_run()


if __name__ == "__main__":
    main()
