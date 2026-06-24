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
    Network: industry/maps_park
    Per turn the game-runner agent picks ONE action and calls
    ProposeAction (a coded_tool that validates + persists the proposal
    to coded_tools/maps_park/state/proposed_action.json). The runner
    reads that file, re-validates, and then commits via direct call to
    the ActionDispatcher coded tool. If pre-validate fails, the runner
    re-prompts the same session with corrective context (env untouched).

  ─ consultant session ────────────────────────────────────────────────
    Network: industry/maps_park_consultant
    Invoked AFTER each step when env_step % CONSULTANT_EVERY == 0
    (default 10) or when verified.done is True. The advisory is captured
    and prepended to the next game-runner prompt.

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

DEFAULT_RUNNER_AGENT = "industry/maps_park"
DEFAULT_CONSULTANT_AGENT = "industry/maps_park_consultant"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8090
DEFAULT_TICK_SECONDS = 5
DEFAULT_MAX_RETRIES = 25
DEFAULT_CONSULTANT_EVERY = 20

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
# Standing user strategy directive (set via --user-strategy). The runner is the
# SOLE writer; agents read it via state_read(name='user_directives') and honor it
# with top precedence — it is never falsified or edited by the consultant.
USER_DIRECTIVES_PATH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "coded_tools", "maps_park", "state", "user_directives.md",
))
USER_DIRECTIVES_NONE = "(none set)"


# ── Bootstrap ────────────────────────────────────────────────────────────────

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
    It does NOT log anything: the caller decides whether the step is accepted
    (then writes the run-log row) or rejected (rolls the env back, writes
    nothing). Logging here would record rolled-back attempts as if they
    happened, corrupting the authoritative run log.
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

def resolve_user_strategy(raw: str | None) -> str:
    """Resolve the --user-strategy value: literal text, or @path to read a file."""
    if not raw:
        return ""
    if raw.startswith("@"):
        path = os.path.expanduser(raw[1:])
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError as exc:  # noqa: BLE001
            print(f"[runner] WARN could not read --user-strategy file {path}: {exc}")
            return ""
    return raw.strip()


def write_user_directives(body: str) -> None:
    """Persist the standing user directive so agents can state_read it each turn."""
    header = "# User strategy directives (standing; honored with top precedence)\n\n"
    with open(USER_DIRECTIVES_PATH, "w", encoding="utf-8") as fh:
        fh.write(header + (body + "\n" if body else USER_DIRECTIVES_NONE + "\n"))


def read_user_directives() -> str:
    """Read the current directive body (sans the header/comment lines).

    Re-read every turn so live edits to the file mid-run take effect on the next
    turn. Returns "" when no directive is set ('(none set)', empty, or missing).
    """
    try:
        with open(USER_DIRECTIVES_PATH, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return ""
    body = "\n".join(ln for ln in lines if not ln.startswith("#")).strip()
    return "" if body == USER_DIRECTIVES_NONE else body


def consult(session, thread, kind: str, verified: dict | None) -> str | None:
    """Invoke the consultant agent; return its advisory string (or None)."""
    ep = verified.get("episode") if verified else None
    step = verified.get("step") if verified else None
    cum = verified.get("cumulative_reward") if verified else None
    final = verified.get("cumulative_reward") if (verified and verified.get("done")) else None
    msg = (
        f"kind={kind} episode={ep} step={step} cumulative_reward={cum} "
        f"final_reward={final}"
    )
    print(f"[consultant] invoking ({kind}) at step={step}")
    response, _thread, tokens = chat(session, thread, msg)
    if tokens:
        print(f"[consultant tokens] total={tokens.get('total_tokens')} "
              f"cost={tokens.get('total_cost')}")
    return (response or "").strip() or None


# ── Main loop ──────────────────────────────────────────────────────────────

def main():
    _bootstrap_env_and_plugins()

    parser = argparse.ArgumentParser(description="maps_park loop runner")
    parser.add_argument("--runner-agent", default=DEFAULT_RUNNER_AGENT)
    parser.add_argument("--consultant-agent", default=DEFAULT_CONSULTANT_AGENT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tick", type=float, default=DEFAULT_TICK_SECONDS,
                        help="Seconds between turns. 0 = no delay.")
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES,
                        help="Max pre/post validation retries before restoring "
                             "the env and re-trying the same step on the next tick.")
    parser.add_argument("--consultant-every", type=int, default=DEFAULT_CONSULTANT_EVERY,
                        help="Invoke the consultant after every N successful steps.")
    parser.add_argument("--no-consultant", action="store_true",
                        help="Skip the consultant entirely (one-network mode for debugging).")
    parser.add_argument("--resume", action="store_true",
                        help="Continuing a prior run: keep existing state/playbook_*.md "
                             "(learned edits survive). Default (fresh start) resets every "
                             "playbook to its config_files seed.")
    parser.add_argument("--user-strategy", default=None,
                        help="Standing user strategy directive. Injected at the top of "
                             "every turn's prompt and honored by the specialists with top "
                             "precedence (above playbooks and active trials); never "
                             "falsified. Pass literal text, or @path to read it from a file.")
    args = parser.parse_args()

    if not args.resume:
        # Clear stale observation cache so each fresh run starts clean.
        if os.path.exists(LATEST_OBS_PATH):
            os.remove(LATEST_OBS_PATH)
            print(f"[runner] Cleared stale observation cache: {LATEST_OBS_PATH}")

        # Clear stale proposal file too.
        if os.path.exists(PROPOSAL_PATH):
            os.remove(PROPOSAL_PATH)


    runner_session, runner_thread = open_session(args.runner_agent, args.host, args.port)
    consultant_session, consultant_thread = (None, None)
    if not args.no_consultant:
        try:
            consultant_session, consultant_thread = open_session(
                args.consultant_agent, args.host, args.port)
        except Exception as exc:  # noqa: BLE001
            print(f"[runner] consultant session failed ({exc}); running without it.")
            consultant_session = None

    # Standing user strategy directive. The runner is the sole writer; agents
    # read it each turn via state_read(name='user_directives') and honor it with
    # top precedence. On a fresh start (or when --user-strategy is given) we
    # (re)write the file so a stale directive from a prior run never leaks in; on
    # --resume with no flag we keep whatever is already there. We also ensure the
    # file always exists so state_read never hits file_not_found.
    user_strategy = resolve_user_strategy(args.user_strategy)
    if args.user_strategy is not None or not args.resume \
            or not os.path.exists(USER_DIRECTIVES_PATH):
        write_user_directives(user_strategy)
        if user_strategy:
            print(f"[runner] User strategy directive set ({len(user_strategy)} chars).")
        else:
            print("[runner] No user strategy directive (file cleared).")

    advisory_for_next_turn: str | None = None
    user_input = "Start the run. Take one action on park 0."
    turn = 0

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

            verified_before = read_last_verified()

            prompt = f"[PREFLIGHT MODE] {preflight_mode}\n\n" + user_input
            if advisory_for_next_turn:
                prompt = (
                    f"[consultant advisory]\n{advisory_for_next_turn}\n[/consultant advisory]\n\n"
                    + prompt
                )
                advisory_for_next_turn = None
            # Standing user directive sits ABOVE the consultant advisory every turn.
            # Re-read the file each turn so live edits mid-run take effect next turn.
            current_directive = read_user_directives()
            if current_directive:
                prompt = (
                    "[USER DIRECTIVE — standing, top priority; overrides playbooks "
                    "and trials]\n" + current_directive + "\n[/USER DIRECTIVE]\n\n"
                    + prompt
                )

            turn_done = False
            last_proposed: dict = {}
            verified_after: dict | None = verified_before
            tokens: dict = {}
            proposal_ok = False

            # Ask the agent for a VALID proposal. Pre-validation does not touch
            # the env, so re-prompting on rejection is cheap and safe — there is
            # no snapshot and no rollback anywhere in this loop.
            for attempt in range(1, args.max_retries + 1):
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

            # Consultant cadence: every N successful steps, plus on episode end.
            if turn_done and consultant_session is not None and verified_after:
                step_n = verified_after.get("step") or 0
                episode_done = bool(verified_after.get("done"))
                if episode_done:
                    advisory_for_next_turn = consult(
                        consultant_session, consultant_thread, "episode_end", verified_after)
                    prev_episode_done = True
                elif args.consultant_every > 0 and step_n > 0 and step_n % args.consultant_every == 0:
                    advisory_for_next_turn = consult(
                        consultant_session, consultant_thread, "periodic", verified_after)

            user_input = "Take one action on park 0."
            if args.tick > 0:
                time.sleep(args.tick)
    except KeyboardInterrupt:
        print("\n[runner] Interrupted; exiting.")


if __name__ == "__main__":
    main()
