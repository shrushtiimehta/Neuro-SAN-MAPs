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
maps_park loop runner.

Drives the `maps_park` agent network turn-by-turn against a running MAPs MCP
server. The director agent calls the MCP `world_server` tool itself to step
the park; this runner just kicks the director on every tick, reuses one
session for the whole run (so each specialist's AgentChecklistMiddleware
preserves its checklist across turns AND across MAPs episodes), and prints
the result.

Prerequisites (run these first in separate shells):

  1. MAPs Node.js backend:
       cd <maps_repo>/MAPs && node map_backend/server.js

  2. MAPs MCP wrapper (from open_gridworld checkout, maps branch):
       python maps_mcp_server.py --layout the_islands --difficulty medium \\
           --mcp_port 8080 --maps_repo_dir <path>/MAPs

  3. neuro-san-studio server:
       python -m run

  4. This runner:
       python -m apps.maps_park.runner
"""

import argparse
import json
import os
import time

from neuro_san.client.agent_session_factory import AgentSessionFactory
from neuro_san.client.streaming_input_processor import StreamingInputProcessor

DEFAULT_AGENT = "industry/maps_park"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 30011
DEFAULT_TICK_SECONDS = 5
DEFAULT_MAX_TURNS = 101  # one full episode by default


def set_up_session(agent_name: str, host: str, port: int):
    factory = AgentSessionFactory()
    session = factory.create_session(
        "direct",
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
    print(f"Connected to {agent_name} session at {host}:{port}.")
    return session, thread


def step(session, thread, message: str):
    processor = StreamingInputProcessor("DEFAULT", "/tmp/maps_park_thinking.txt", session, None)
    thread["user_input"] = message
    thread = processor.process_once(thread)
    token_accounting = processor.processor.get_token_accounting()
    return thread.get("last_chat_response"), thread, token_accounting


def read_last_verified(log_path: str) -> dict | None:
    """Return the last non-empty row from run.jsonl as ground-truth."""
    if not os.path.exists(log_path):
        return None
    last = None
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last = json.loads(line)
    except (OSError, json.JSONDecodeError):
        pass
    return last


def main():
    parser = argparse.ArgumentParser(description="maps_park loop runner")
    parser.add_argument("--agent", default=DEFAULT_AGENT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--tick", type=float, default=DEFAULT_TICK_SECONDS,
                        help="Seconds between turns. 0 means no delay.")
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS,
                        help="Stop after this many turns. 0 means run forever.")
    args = parser.parse_args()

    log_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "maps_park", "run.jsonl"))
    obs_file = os.path.join(os.path.dirname(__file__), "..", "..", "memory", "maps_park", "latest_observations.json")
    obs_path = os.path.normpath(obs_file)
    if os.path.exists(obs_path):
        os.remove(obs_path)
        print(f"Cleared stale observation cache: {obs_path}")

    session, thread = set_up_session(args.agent, args.host, args.port)

    user_input = "Start the run. Take one action on park 0."
    turn = 0
    try:
        while True:
            turn += 1
            print(f"\n========== TURN {turn} ==========")
            response, thread, tokens = step(session, thread, user_input)
            print(response or "(no response)")
            if tokens:
                total = tokens.get("total_tokens", "?")
                cost = tokens.get("total_cost", "?")
                prompt = tokens.get("prompt_tokens", "?")
                completion = tokens.get("completion_tokens", "?")
                print(f"[tokens] total={total}  prompt={prompt}  completion={completion}  cost=${cost:.4f}")
            verified = read_last_verified(log_path)
            if verified and verified.get("step") is not None:
                v_step  = verified.get("step", "?")
                v_cash  = verified.get("cash", "?")
                v_rew   = verified.get("reward", "?")
                v_cum   = verified.get("cumulative_reward", "?")
                v_act   = verified.get("action", "?")
                v_done  = verified.get("done", False)
                print(f"[verified] step={v_step}/100  action={v_act}  cash=${v_cash}"
                      f"  reward={v_rew}  cumulative={v_cum}"
                      + ("  EPISODE DONE" if v_done else ""))
            else:
                print("[verified] no ground-truth row yet (run.jsonl empty or fields null)")
            user_input = "Take one action on park 0."
            if args.max_turns and turn >= args.max_turns:
                print(f"\nReached max_turns={args.max_turns}; stopping.")
                break
            if args.tick > 0:
                time.sleep(args.tick)
    except KeyboardInterrupt:
        print("\nInterrupted; exiting.")


if __name__ == "__main__":
    main()
