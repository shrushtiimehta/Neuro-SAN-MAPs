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
    Network: maps_park
    Per turn the game-runner agent picks ONE action and calls
    ProposeAction (a coded_tool that validates + persists the proposal
    to coded_tools/maps_park/state/proposed_action.json). The runner
    reads that file, re-validates, and then commits via direct call to
    the ActionDispatcher coded tool. If pre-validate fails, the runner
    re-prompts the same session with corrective context (env untouched).

  ─ consultant sessions (two networks) ────────────────────────────────
    The old single consultant network was split in two:
      • micro  (maps_park_micro)  — mid-episode analysis.
        Invoked AFTER each step when env_step % MICRO_EVERY == 0
        (default 10), i.e. at steps 10,20,...,90 of the 100-step episode.
        Logs trials for the current episode, and emits a health VERDICT
        (on_track|underperforming|doomed) judged against the best-ever
        episode. A 'doomed' verdict at/after step 50 makes the runner ABORT
        the episode at once; before step 50 it grants one more checkpoint
        (~MICRO_EVERY steps) to recover, aborting on two consecutive 'doomed'
        verdicts. Aborting stops soliciting the game-runner and fast-forwards
        to done with wait()s (the MAPs env has no early-reset tool), booking
        the loss. The next episode's
        macro start then regenerates the strategy from the best episode
        (rollback) and the aborted trials are falsified at close-out.
      • macro  (maps_park_macro)  — start- AND end-of-episode work.
        At episode START (fired before turn 1 of each new episode) it
        compares the best-ever episode against the last one, writes the
        episode checklist + coordinator strategy summary, demotes stale
        learned rules, and logs fresh trials. At episode END (verified.done
        is True — step 100 or an earlier terminated episode) it runs the
        thin close-out (promote/resolve this episode's trials,
        advance_episode).
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

# The MCP SDK's streamable-HTTP client logs "Received session ID" and
# "Negotiated protocol version" at INFO on every (re)connect to the
# maps_mcp_server. That handshake chatter buries the runner's own output, so
# pin that logger to WARNING.
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor

from coded_tools.maps_park.action_dispatcher import ActionDispatcher
from coded_tools.maps_park.seed_playbooks import SeedPlaybooks


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_RUNNER_AGENT = "maps_park"
# The consultant was split into two networks: a mid-episode micro analyzer and
# an end-of-episode macro analyzer (close-out + whole-run synthesis).
DEFAULT_MICRO_AGENT = "maps_park_micro"
DEFAULT_MACRO_AGENT = "maps_park_macro"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8090
DEFAULT_TICK_SECONDS = 5
DEFAULT_MAX_RETRIES = 25
# Micro analyzer cadence: every 10 successful steps -> steps 10,20,...,90.
DEFAULT_MICRO_EVERY = 10

# Early-abort guardrail. At each micro checkpoint the analyzer judges the run
# against the BEST-ever episode's leading indicators and emits a
# "VERDICT: on_track|underperforming|doomed" line the runner parses. How a
# 'doomed' verdict is acted on depends on how far the 100-step episode has run:
#   • at/after ABORT_HALFWAY_STEP -> abort immediately (a single strike). Half
#     the episode is already gone; there is no runway left to recover.
#   • before ABORT_HALFWAY_STEP   -> grant ~micro_every more steps (one extra
#     checkpoint) to recover; abort only on ABORT_MIN_STRIKES consecutive strikes.
#   • before ABORT_EARLIEST_STEP  -> ignored (reward is always low this early, so
#     a doom call here is noise).
# Aborting fast-forwards the rest of the episode with wait()s — booking the loss
# cheaply instead of burning LLM calls on a run that cannot clear the floor.
# Rollback is emergent: the next episode's macro start regenerates the strategy
# summary from the BEST episode, and the aborted trials are falsified at close-out.
DEFAULT_REWARD_FLOOR = 300000   # cum_reward a run must plausibly clear by step 100
DEFAULT_REWARD_GOAL = 1000000   # the north-star target the whole run chases
# ponytail: need enough signal before trusting a doom call; value compounds in
# the back half so early steps are always low. Bump if runs get killed too soon.
ABORT_EARLIEST_STEP = 30
ABORT_HALFWAY_STEP = 50         # at/after this step a single 'doomed' aborts at once
ABORT_MIN_STRIKES = 2           # consecutive 'doomed' verdicts to abort BEFORE halfway

PROPOSAL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "coded_tools", "maps_park", "state", "proposed_action.json",
)
# Per-episode run logs: one file per episode (run.ep<NNN>.jsonl) so an
# episode is never split across files. The runner is the SOLE writer.
RUN_LOG_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "logs", "maps_park",
))
TURNS_LOG_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "logs", "maps_park", "turns.jsonl",
))
LATEST_OBS_PATH = os.environ.get(
    "MAPS_LATEST_OBS_PATH",
    os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..",
        "coded_tools", "maps_park", "state", "latest_observations.json",
    )),
)
# Agent reasoning capture. Honor the studio's THINKING_FILE / THINKING_DIR env
# vars when present; otherwise default to the standard logs/ locations so the
# runner populates the same paths the studio does (was previously a throwaway
# /tmp file with thinking_dir disabled, so no per-agent maps were ever written).
THINKING_FILE = os.environ.get(
    "THINKING_FILE",
    os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "logs", "agent_thinking.txt",
    )),
)
THINKING_DIR = os.environ.get(
    "THINKING_DIR",
    os.path.normpath(os.path.join(
        os.path.dirname(__file__), "..", "..", "logs", "thinking_dir",
    )),
)
# Env-coupled episode state. On a fresh (non --resume) start this is deleted
# so the run doesn't inherit the prior run's reward baseline: a missing
# last_reward makes episode-0 prior_reward default to 0.
LAST_REWARD_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "coded_tools", "maps_park", "state", "last_reward.md",
))

# Playbook state dir + snapshot archive. Playbooks evolve each episode
# (start-of-episode plan + close-out promotions), so we snapshot them into
# state/playbook_history/<ts>_<tag>/ at both the start (ep<NNN>_pre) and end
# (ep<NNN>_post) of every episode — plus once before a fresh run reseeds them
# (prerun). Snapshots are append-only; nothing is ever deleted.
PLAYBOOK_STATE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "coded_tools", "maps_park", "state",
))
PLAYBOOK_HISTORY_DIR = os.path.join(PLAYBOOK_STATE_DIR, "playbook_history")


# ── Bootstrap ────────────────────────────────────────────────────────────────


def snapshot_playbooks(tag: str) -> str | None:
    """Copy state/playbook_*.md into state/playbook_history/<ts>_<tag>/.

    Called at each episode boundary (tag ep<NNN>_pre / ep<NNN>_post) and once
    before a fresh run reseeds (tag 'prerun'). Append-only — never deletes. The
    timestamp prefix keeps every snapshot distinct. Returns the snapshot dir,
    or None if there were no non-empty playbooks to save.
    """
    sources = [p for p in sorted(glob.glob(os.path.join(PLAYBOOK_STATE_DIR, "playbook_*.md")))
               if os.path.getsize(p) > 0]
    if not sources:
        return None
    dest = os.path.join(PLAYBOOK_HISTORY_DIR, f"{time.strftime('%Y%m%d-%H%M%S')}_{tag}")
    os.makedirs(dest, exist_ok=True)
    for src in sources:
        shutil.copy2(src, os.path.join(dest, os.path.basename(src)))
    return dest

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


def chat(session, thread, message: str):
    os.makedirs(THINKING_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(THINKING_FILE) or ".", exist_ok=True)
    processor = StreamingInputProcessor("DEFAULT", THINKING_FILE, session, THINKING_DIR)
    thread["user_input"] = message
    thread = processor.process_once(thread)
    return thread.get("last_chat_response"), thread, processor.processor.get_token_accounting()


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
    for path in glob.glob(os.path.join(RUN_LOG_DIR, "run.ep*.jsonl")):
        match = re.search(r"run\.ep(\d+)\.jsonl$", os.path.basename(path))
        if match:
            out.append((int(match.group(1)), path))
    return sorted(out)


def latest_episode_log() -> str | None:
    """Path to the highest-numbered episode log, or None if none exist."""
    logs = _all_episode_logs()
    return logs[-1][1] if logs else None


def read_last_verified() -> dict | None:
    """Last non-empty row from the current episode's log as ground truth."""
    path = latest_episode_log()
    if not path or not os.path.exists(path):
        return None
    last = None
    try:
        with open(path, "r", encoding="utf-8") as fh:
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


def build_run_row(args: dict, envelope: dict) -> dict:
    """Reshape a post-step envelope into the authoritative run-log row.

    Pure transform, no I/O — the caller writes the row only once the step is
    accepted. Dropped fields (wall_time/tool/park/horizon) were redundant
    (single tool, single park, constant horizon, wall_time unused).
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

    def first_set(*values: Any) -> Any:
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
        "cumulative_reward": first_set(envelope.get("cumulative_reward"), obs.get("cumulative_reward")),
        "reward": first_set(envelope.get("reward"), obs.get("reward")),
        "done": bool(envelope.get("done")),
        "error": envelope.get("error"),
        "num_rides": rides.get("total_rides"),
        "num_shops": shops.get("total_shops"),
        "num_staff": len(staff.get("staff_list") or []),
        "min_uptime": rides.get("min_uptime"),
        "min_cleanliness": obs.get("min_cleanliness"),
        "shop_revenue": shops.get("total_revenue_generated"),
        "ride_op_cost": rides.get("total_operating_cost"),
        **{k: v for k, v in flat_args.items() if k not in {"park", "action", "args"}},
    }
    return row


# ── Consultant invocation ──────────────────────────────────────────────────

# The micro analyzer's mid-episode reply begins with this line; the runner
# parses it to drive the early-abort guardrail.
_VERDICT_RE = re.compile(r"VERDICT:\s*(on[_ ]?track|underperforming|doomed)", re.I)


def _parse_verdict(advisory: str | None) -> str | None:
    """Pull the micro's health verdict from its advisory, or None if absent.

    A missing/unparseable verdict returns None, which the abort state machine
    treats as a no-op — the runner NEVER aborts a run on a parse miss.
    """
    if not advisory:
        return None
    match = _VERDICT_RE.search(advisory)
    if not match:
        return None
    verdict = match.group(1).lower().replace(" ", "_")
    return "on_track" if verdict == "ontrack" else verdict


def _doom_decision(strikes: int, verdict: str | None, step: int) -> tuple[int, bool]:
    """Fold one micro verdict into the abort state machine.

    Returns (new_strike_count, should_abort). A 'doomed' verdict at/after
    ABORT_EARLIEST_STEP adds a strike; whether it aborts depends on the step:
    at/after ABORT_HALFWAY_STEP a single strike aborts immediately (no runway
    left to recover), while before halfway it takes ABORT_MIN_STRIKES consecutive
    strikes (one extra ~micro_every-step checkpoint of grace). Any non-doomed
    verdict resets the count; an unknown/None verdict (or a doom call before
    ABORT_EARLIEST_STEP) is a no-op.
    """
    if step >= ABORT_EARLIEST_STEP and verdict == "doomed":
        strikes += 1
        required = 1 if step >= ABORT_HALFWAY_STEP else ABORT_MIN_STRIKES
        return strikes, strikes >= required
    if verdict in ("on_track", "underperforming"):
        return 0, False
    return strikes, False


def consult(session, thread, kind: str, verified: dict | None,
            label: str = "consultant", extra: str = "") -> str | None:
    """Invoke a consultant network (micro or macro); return its advisory (or None).

    `label` is purely cosmetic (which network is being called) for the logs;
    the agent routes on `kind` (periodic -> micro; episode_start / episode_end
    -> macro). `extra` is appended verbatim to the message (e.g. the reward
    floor/goal on periodic, or the aborted flag on episode_end).
    """
    ep = verified.get("episode") if verified else None
    step = verified.get("step") if verified else None
    cum = verified.get("cumulative_reward") if verified else None
    final = verified.get("cumulative_reward") if (verified and verified.get("done")) else None
    msg = (
        f"kind={kind} episode={ep} step={step} cumulative_reward={cum} "
        f"final_reward={final}"
    )
    if extra:
        msg += " " + extra
    print(f"[{label}] invoking ({kind}) at episode={ep} step={step}")
    response, _thread, tokens = chat(session, thread, msg)
    if tokens:
        print(f"[{label} tokens] total={tokens.get('total_tokens')} "
              f"cost={tokens.get('total_cost')}")
    return (response or "").strip() or None


# ── One-shot consult mode ────────────────────────────────────────────────────

def run_consult_only(args) -> None:
    """Invoke a single analyzer network once against the latest episode log.

    Runs NO game loop and performs none of the runner's fresh-start resets, so
    playbooks/state are left exactly as the cancelled run left them. Assumes the
    studio server + MAPs env are already up (e.g. booted by run_macro.sh).

    For 'macro' the message uses kind=episode_end, which drives the network's
    full close-out (cross-run analysis + promote/resolve trials + advance_episode)
    — the same side effects a normal episode end has. The latest run.ep*.jsonl is
    read as context even when its last row has done=false (a cancelled episode).
    """
    kind = "episode_end" if args.consult_only == "macro" else "periodic"
    agent_name = args.macro_agent if args.consult_only == "macro" else args.micro_agent

    # This path skips the normal startup seed, so ensure the trial-ledger files
    # exist before the analyzer reads them — otherwise the macro errors on a
    # missing trial_strategies_outcome.md. overwrite=False never clobbers the
    # cancelled run's learned playbooks (they exist and are skipped); in practice
    # this just create-if-absents the ledgers.
    seed = SeedPlaybooks().invoke({"overwrite": False}, {})
    if seed.get("trial_ledgers_created"):
        print(f"[runner] Initialized missing trial ledgers: {seed['trial_ledgers_created']}")
    if seed.get("errors"):
        print(f"[runner] WARN seed errors: {seed['errors']}")

    try:
        session, thread = open_session(agent_name, args.host, args.port)
    except Exception as exc:  # noqa: BLE001
        print(f"[runner] Could not connect to '{agent_name}' at "
              f"{args.host}:{args.port}: {exc}")
        print("[runner] Is the studio server up? Boot the backend with "
              "apps/maps_park/run_macro.sh.")
        return
    verified = read_last_verified()
    if verified is None:
        print("[runner] WARN: no run.ep*.jsonl found; invoking with empty context.")
    else:
        print(f"[runner] consult-only ({args.consult_only}) against "
              f"episode={verified.get('episode')} step={verified.get('step')} "
              f"done={verified.get('done')}")
    advisory = consult(session, thread, kind, verified, label=args.consult_only)
    print("\n" + "=" * 70)
    print(f"[{args.consult_only}] advisory:\n")
    print(advisory or "(no advisory returned)")


# ── Main loop ──────────────────────────────────────────────────────────────

def main():
    _bootstrap_env_and_plugins()

    parser = argparse.ArgumentParser(description="maps_park loop runner")
    parser.add_argument("--runner-agent", default=DEFAULT_RUNNER_AGENT)
    parser.add_argument("--micro-agent", default=DEFAULT_MICRO_AGENT,
                        help="Mid-episode (kind=periodic) analyzer network.")
    parser.add_argument("--macro-agent", default=DEFAULT_MACRO_AGENT,
                        help="End-of-episode (kind=episode_end) close-out + "
                             "whole-run analyzer network.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tick", type=float, default=DEFAULT_TICK_SECONDS,
                        help="Seconds between turns. 0 = no delay.")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
                        help="Max pre/post validation retries before restoring "
                             "the env and re-trying the same step on the next tick.")
    parser.add_argument("--micro-every", type=int, default=DEFAULT_MICRO_EVERY,
                        help="Invoke the micro analyzer after every N successful "
                             "steps (default 10 -> steps 10,20,...,90).")
    parser.add_argument("--reward-floor", type=int, default=DEFAULT_REWARD_FLOOR,
                        help="cum_reward a run must plausibly clear by step 100. "
                             "Passed to the micro, which judges 'doomed' against "
                             "this and the best episode's trajectory.")
    parser.add_argument("--reward-goal", type=int, default=DEFAULT_REWARD_GOAL,
                        help="North-star cum_reward target for the run; passed to "
                             "the micro for context.")
    parser.add_argument("--consult-only", choices=("macro", "micro"),
                        nargs="?", const="macro", default=None,
                        help="Run NO game loop: invoke one analyzer network a single "
                             "time against the latest episode log, print its advisory, "
                             "and exit. Bare --consult-only defaults to 'macro', which "
                             "fires the full episode-end close-out (cross-run analysis + "
                             "promote/resolve trials + advance_episode) — same side "
                             "effects as a normal episode end. Pass 'micro' for the "
                             "mid-episode analyzer instead. Use apps/maps_park/run_macro.sh "
                             "to boot the backend (in --resume mode) and run this in one step.")
    parser.add_argument("--resume", action="store_true",
                        help="Continuing a prior run: keep existing state/playbook_*.md "
                             "(learned edits survive). Default (fresh start) resets every "
                             "playbook to its config_files seed.")
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
    try:
        micro_session, micro_thread = open_session(
            args.micro_agent, args.host, args.port)
    except Exception as exc:  # noqa: BLE001
        print(f"[runner] micro analyzer session failed ({exc}); running without it.")
        micro_session = None
    try:
        macro_session, macro_thread = open_session(
            args.macro_agent, args.host, args.port)
    except Exception as exc:  # noqa: BLE001
        print(f"[runner] macro analyzer session failed ({exc}); running without it.")
        macro_session = None

    advisory_for_next_turn: str | None = None
    user_input = "Start the run. Take one action on park 0."
    turn = 0

    # Fresh start reseeds the playbooks from config below (overwrite=True),
    # discarding the finished run's learned edits — so snapshot them first as
    # 'prerun'. --resume keeps the working copies, so there is nothing to save.
    if not args.resume:
        snap = snapshot_playbooks("prerun")
        if snap:
            print(f"[runner] Snapshotted prior-run playbooks to {snap}")

    # Startup seed: lay down the six playbooks before the first turn via the
    # SeedPlaybooks coded tool (deterministic file copy, no LLM). A fresh start
    # resets every playbook to its config_files seed; --resume keeps the
    # existing working copies so learned edits survive.
    seed_result = SeedPlaybooks().invoke({"overwrite": not args.resume}, {})
    print(f"[runner] Playbooks seeded={seed_result['seeded']} "
          f"skipped={seed_result['skipped']} errors={seed_result['errors']}")

    # Fresh start (not --resume): drop the env-coupled episode state so the run
    # doesn't inherit the prior run's reward baseline. A missing last_reward
    # makes episode-0 prior_reward default to 0. --resume keeps it to continue
    # the in-flight episode.
    if not args.resume:
        if os.path.exists(LAST_REWARD_PATH):
            os.remove(LAST_REWARD_PATH)
            print(f"[runner] Fresh start: cleared {os.path.basename(LAST_REWARD_PATH)}")

    prev_episode_done = False
    # Episode number for the upcoming episode's start-of-episode macro pass.
    # turn 1 is episode 0; bumped to ended_episode+1 when an episode finishes.
    next_episode_num = 0

    # Early-abort state (per episode; reset on every fresh episode below).
    aborting = False
    abort_reason = ""
    doom_strikes = 0

    try:
        while True:
            turn += 1
            print(f"\n========== TURN {turn} ==========")

            # The runner authoritatively knows when an episode is fresh: the
            # process just started (turn 1) or the prior turn ended an episode.
            # The preflight custodian consumes this explicit mode instead of
            # re-inferring "fresh" from step==1.
            preflight_mode = "fresh_episode" if (turn == 1 or prev_episode_done) else "continue"

            # A fresh episode clears any abort/doom state carried from the prior
            # one (the loss is already booked; this episode starts clean).
            if preflight_mode == "fresh_episode":
                aborting = False
                abort_reason = ""
                doom_strikes = 0

            # If the previous turn ended an episode, ensure the new episode's
            # playbooks exist before the game-runner acts. overwrite=False:
            # learned edits promoted at the prior episode's close survive.
            if prev_episode_done:
                roll = SeedPlaybooks().invoke({"overwrite": False}, {})
                if roll["seeded"]:
                    print(f"[runner] New-episode playbooks created: {roll['seeded']}")
                prev_episode_done = False

            # Start-of-episode MACRO pass: compare the best-ever episode against
            # the last one, WriteEpisodePlan the checklist + coordinator strategy
            # summary, demote regression-linked learned rules, and log fresh
            # trials — all BEFORE park_director acts on turn 1. Skipped when
            # resuming an in-flight episode (turn 1 + --resume is a continuation,
            # not a genuine new episode).
            if (preflight_mode == "fresh_episode" and macro_session is not None
                    and not (turn == 1 and args.resume)):
                start_ctx = {"episode": next_episode_num, "step": 0,
                             "cumulative_reward": 0, "done": False}
                consult(macro_session, macro_thread, "episode_start",
                        start_ctx, label="macro-start")

            # BEFORE the episode starts: snapshot the playbooks the game-runner
            # will act on (the start-of-episode plan just written, plus the prior
            # episode's close-out promotions) as ep<NNN>_pre.
            if preflight_mode == "fresh_episode":
                snap = snapshot_playbooks(f"ep{next_episode_num:03d}_pre")
                if snap:
                    print(f"[runner] Snapshotted ep{next_episode_num} pre-episode playbooks to {snap}")

            verified_before = read_last_verified()

            prompt = f"[PREFLIGHT MODE] {preflight_mode}\n\n" + user_input
            if advisory_for_next_turn:
                prompt = (
                    f"[consultant advisory]\n{advisory_for_next_turn}\n[/consultant advisory]\n\n"
                    + prompt
                )
                advisory_for_next_turn = None
            turn_done = False
            last_proposed: dict = {}
            verified_after: dict | None = verified_before
            tokens: dict = {}
            proposal_ok = False

            # Doomed run (micro verdict): skip all LLM solicitation and fast-
            # forward this episode with wait() until the env reports done. The
            # MAPs env has no early-reset MCP tool (only snapshot/restore), so
            # reaching step 100 via waits is the only way to end the episode and
            # begin a fresh one. The loss is booked; the next episode's macro
            # start regenerates the strategy from the BEST episode (rollback) and
            # the aborted trials are falsified at close-out.
            if aborting:
                print(f"[runner] ABORTING (doomed): {abort_reason} — advancing with wait().")
                last_proposed = {"park": 0, "action": "wait", "args": {}}
                proposal_ok = True

            # Ask the agent for a VALID proposal. Pre-validation does not touch
            # the env, so re-prompting on rejection is cheap and safe — there is
            # no snapshot and no rollback anywhere in this loop.
            for attempt in range(1, args.max_retries + 1):
                if aborting:
                    break
                # Clear the proposal file so we know the agent wrote a fresh one.
                if os.path.exists(PROPOSAL_PATH):
                    os.remove(PROPOSAL_PATH)

                response, runner_thread, tokens = chat(runner_session, runner_thread, prompt)
                print(f"[runner reply attempt={attempt}] " + (response or "(no response)"))

                proposal_envelope = read_proposal()
                if proposal_envelope is None:
                    prompt = (
                        "ERROR: you did not call ProposeAction this turn. "
                        "Call ProposeAction exactly once with action and args."
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
                    f"ERROR: ProposeAction rejected your proposed action. "
                    f"Reasons: {reasons}. The env was NOT touched. "
                    f"Pick a different concrete action and call ProposeAction again."
                )

            # If the agent never produced a valid proposal, advance the day with
            # a wait() instead of getting stuck or rolling anything back.
            if not proposal_ok:
                print(f"[runner] No valid proposal after {args.max_retries} attempts; "
                      f"advancing the day with wait().")
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
                candidate = build_run_row(last_proposed, dispatch_envelope)
                env_err = candidate.get("error")
                if env_err:
                    candidate["rejected_action"] = candidate.get("action")
                    candidate["action"] = "wait"
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
                    f"reward={candidate.get('reward')}  "
                    f"cum={candidate.get('cumulative_reward')}  {status}"
                    + ("  EPISODE DONE" if candidate.get("done") else "")
                )
                if env_err:
                    advisory_for_next_turn = (
                        f"NOTE: your previous action ({candidate.get('rejected_action')}) was "
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
            with open(TURNS_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(turn_record, default=str) + "\n")
                fh.flush()

            # Analyzer cadence. On the done=true row -> macro network (episode
            # close-out + whole-run analysis). Otherwise, every N successful
            # steps (10,20,...,90) -> micro network (mid-episode analysis).
            # Step 100 is done=true, so macro wins there and the two never
            # collide. Each fires only if its session opened.
            if turn_done and verified_after:
                step_n = verified_after.get("step") or 0
                episode_done = bool(verified_after.get("done"))
                if episode_done:
                    if macro_session is not None:
                        # Tell the close-out whether the episode was aborted so it
                        # falsifies the doomed run's active trials (rather than
                        # leaving them inconclusive, which would carry them over).
                        extra = (f"aborted=true reason={abort_reason}" if aborting
                                 else "aborted=false")
                        advisory_for_next_turn = consult(
                            macro_session, macro_thread, "episode_end",
                            verified_after, label="macro", extra=extra)
                    # AFTER the episode ends: snapshot the playbooks the close-out
                    # just promoted into (its confirmed-trial learned rules) as
                    # ep<NNN>_post — the episode's final learned state.
                    ended_ep = verified_after.get("episode") or 0
                    snap = snapshot_playbooks(f"ep{ended_ep:03d}_post")
                    if snap:
                        print(f"[runner] Snapshotted ep{ended_ep} post-episode playbooks to {snap}")
                    prev_episode_done = True
                    # Next loop iteration is a fresh episode; its start pass
                    # plans episode (ended_episode + 1).
                    next_episode_num = (verified_after.get("episode") or 0) + 1
                elif (not aborting and micro_session is not None and args.micro_every > 0
                        and step_n > 0 and step_n % args.micro_every == 0):
                    advisory_for_next_turn = consult(
                        micro_session, micro_thread, "periodic",
                        verified_after, label="micro",
                        extra=f"floor={args.reward_floor} goal={args.reward_goal}")
                    # Fold the micro's health verdict into the abort guardrail.
                    verdict = _parse_verdict(advisory_for_next_turn)
                    doom_strikes, do_abort = _doom_decision(doom_strikes, verdict, step_n)
                    if do_abort:
                        aborting = True
                        abort_reason = f"micro verdict 'doomed' x{doom_strikes} by step {step_n}"
                        print(f"[runner] ABORT TRIGGERED: {abort_reason}")
                    elif verdict == "doomed":
                        print(f"[runner] doom strike {doom_strikes}/{ABORT_MIN_STRIKES} "
                              f"at step {step_n} (~{args.micro_every}-step grace to recover)")

            user_input = "Take one action on park 0."
            if args.tick > 0:
                time.sleep(args.tick)
    except KeyboardInterrupt:
        print("\n[runner] Interrupted; exiting.")


if __name__ == "__main__":
    main()
