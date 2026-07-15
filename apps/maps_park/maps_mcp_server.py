#!/usr/bin/env python3
"""
maps_mcp_server.py — MCP server wrapping the MAPs Mini Amusement Park benchmark.

Exposes a single MCP tool (`world_server`) that:
  - Accepts a MAPs action string as `user_message.text`
  - Steps the park environment
  - Returns the concise park observation as JSON

The tool name `world_server` matches the default expected by OpenGridWorld's
ExternalRequestManager, so no extra configuration is needed on the OGW side.

Vendored into neuro-san-studio from open_gridworld (branch `maps`); it is
self-contained (no open_gridworld package imports). apps/maps_park/run_all.sh
launches it — you normally do not run it by hand.

Usage:
  python apps/maps_park/maps_mcp_server.py --layout the_islands --difficulty medium --mcp_port 8765
  python apps/maps_park/maps_mcp_server.py --tl_callback_url http://localhost:9000/incoming

  # Point to a non-default MAPs repo location:
  python maps_mcp_server.py --maps_repo_dir /path/to/mini_amusement_parks/MAPs

Prerequisites:
  1. MAPs Node.js backend running:
       cd <maps_repo_dir> && node map_backend/server.js   (default port 3000)
  2. pip install "mcp[cli]" requests   (into whatever Python env runs this script)
  3. MAPs Python deps installed (map_py package present in maps_repo_dir)
"""

import argparse
import json
import os
import pickle
import sys
import time
import uuid

import requests
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel


# ── Observation helper (adapted from first_agent.py) ─────────────────────────

def make_concise_obs(obs) -> dict:
    """
    Build the observation dict sent to agents.

    Pre-computes valid_placement_coords: empty tiles 4-directionally adjacent
    to path tiles that are REACHABLE FROM THE ENTRANCE (connected component).
    This prevents agents from placing entities on disconnected islands where
    guests can never reach them (which would earn $0 revenue forever).
    """
    d = obs.model_dump() if hasattr(obs, "model_dump") else obs
    park_size = 20

    path_set: set[tuple[int, int]] = {(p["x"], p["y"]) for p in d.get("paths", [])}
    water_set: set[tuple[int, int]] = {(w["x"], w["y"]) for w in d.get("waters", [])}

    def _coord(val) -> tuple[int, int]:
        if isinstance(val, (list, tuple)):
            return (val[0], val[1])
        if isinstance(val, dict):
            return (val.get("x", -1), val.get("y", -1))
        return (-1, -1)

    entrance_coord = _coord(d.get("entrance"))
    exit_coord = _coord(d.get("exit"))
    blocked = {entrance_coord, exit_coord}

    occupied: set[tuple[int, int]] = set()
    for entity_list in [
        (d.get("rides") or {}).get("ride_list", []),
        (d.get("shops") or {}).get("shop_list", []),
        (d.get("staff") or {}).get("staff_list", []),
    ]:
        for e in entity_list:
            if isinstance(e, dict) and "x" in e and "y" in e:
                occupied.add((e["x"], e["y"]))

    # BFS from entrance to find only reachable path tiles
    walkable = path_set | {entrance_coord, exit_coord}
    reachable: set[tuple[int, int]] = set()
    if entrance_coord in walkable:
        frontier = [entrance_coord]
        reachable.add(entrance_coord)
        while frontier:
            cx, cy = frontier.pop()
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nb = (cx + dx, cy + dy)
                if nb not in reachable and nb in walkable:
                    reachable.add(nb)
                    frontier.append(nb)

    candidates: set[tuple[int, int]] = set()
    for px, py in reachable:
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nx, ny = px + dx, py + dy
            if 0 <= nx < park_size and 0 <= ny < park_size:
                candidates.add((nx, ny))

    invalid = path_set | water_set | blocked | occupied
    valid_placements = sorted(candidates - invalid)

    staff_occupied = {
        (e["x"], e["y"])
        for e in (d.get("staff") or {}).get("staff_list", [])
        if isinstance(e, dict) and "x" in e and "y" in e
    }
    available_path_coords = sorted((reachable & path_set) - staff_occupied)

    return {
        "step":                    d.get("step"),
        "horizon":                 d.get("horizon"),
        "money":                   d.get("money"),
        "value":                   d.get("value"),
        "park_rating":             d.get("park_rating"),
        "available_entities":      d.get("available_entities"),
        "research_speed":          d.get("research_speed"),
        "research_topics":         d.get("research_topics"),
        "research_operating_cost": d.get("research_operating_cost"),
        "entrance":                d.get("entrance"),
        "exit":                    d.get("exit"),
        "valid_placement_coords":  [[x, y] for x, y in valid_placements],
        "path_coords":             [[x, y] for x, y in available_path_coords],
        "rides":                   d.get("rides"),
        "shops":                   d.get("shops"),
        "staff":                   d.get("staff"),
        "min_cleanliness":         d.get("min_cleanliness"),
        "guest_survey_results":    d.get("guest_survey_results"),
    }


# ── Game manager ──────────────────────────────────────────────────────────────

class GameManager:
    """Manages a single park slot. Each time the episode ends the slot restarts
    automatically. slot_index is fixed (0-based park number); episode_count
    increments with each restart."""

    def __init__(self, slot_index: int, maps_host: str, maps_port: int,
                 layout: str, difficulty: str, max_steps: int):
        self.slot_index = slot_index
        self.maps_host = maps_host
        self.maps_port = maps_port
        self.layout = layout
        self.difficulty = difficulty
        self.max_steps = max_steps

        self._game_ctx = None
        self.game = None
        self.obs = None
        self.step_count = 0
        self.total_reward = 0.0
        self.done = False
        self.episode_count = 0  # increments each time this slot restarts

    def start(self):
        # Deferred import — map_py is only on sys.path after main() adds maps_repo_dir
        from map_py.mini_amusement_park import MiniAmusementPark

        self._game_ctx = MiniAmusementPark(
            host=self.maps_host,
            port=str(self.maps_port),
            render_park=False,
            observation_type="pydantic",
            return_raw_in_info=True,
            layout=self.layout,
            difficulty=self.difficulty,
        )
        self.game = self._game_ctx.__enter__()
        self.obs, _ = self.game.reset()
        self.step_count = 0
        self.total_reward = 0.0
        self.done = False
        print(
            f"[MAPs Server] Park slot {self.slot_index} episode {self.episode_count + 1} "
            f"initialised. Layout={self.layout}, difficulty={self.difficulty}"
        )

    def step(self, action_str: str) -> dict:
        self.obs, reward, terminated, truncated, info = self.game.step(action_str)
        self.step_count += 1
        self.total_reward += float(reward)
        episode_done = terminated or truncated or (self.step_count >= self.max_steps)

        error = None
        if isinstance(info, dict) and "error" in info:
            error = info["error"]

        concise = make_concise_obs(self.obs)

        status = "✗ REJECTED" if error else f"✓ reward={float(reward):+.0f}"
        print(
            f"[MAPs Server] Park {self.slot_index} ep{self.episode_count + 1} "
            f"step {self.step_count}: {action_str[:60]}  →  {status}  "
            f"money=${concise.get('money')}  value=${concise.get('value')}"
        )

        if episode_done:
            completed_episode = self.episode_count
            final_step = self.step_count
            final_total_reward = self.total_reward
            final_value = concise.get("value")

            # Persist the completed episode's trajectory TSV + its park_id so
            # each run's TSVs land next to its run.ep*.jsonl logs. Must happen
            # BEFORE close() (close deletes the backend park). Best-effort: a
            # save failure must never break the episode loop.
            # ponytail: only fires on clean episode end; a Ctrl-C'd in-flight
            # episode isn't saved (its jsonl is partial too). Add atexit if needed.
            if _trajectory_dir:
                try:
                    save_res = self.game.save_trajectory(
                        save_local=True,
                        save_path=os.path.join(_trajectory_dir, "traj.tsv"),
                    )
                    tsv_path = save_res.get("localPath") if isinstance(save_res, dict) else None
                    ledger = os.path.join(_trajectory_dir, "park_ids.jsonl")
                    # Global episode number = count of prior ledger entries, so it
                    # stays unique across runs (completed_episode resets to 0 on
                    # each fresh run). ponytail: re-reads the ledger each episode
                    # end; fine at ~1-per-100-steps cadence, single writer.
                    global_ep = 0
                    if os.path.exists(ledger):
                        with open(ledger) as f:
                            global_ep = sum(1 for line in f if line.strip())
                    with open(ledger, "a") as f:
                        f.write(json.dumps({
                            "episode":     global_ep,
                            "run_episode": completed_episode,
                            "park_id":     self.game.park_id,
                            "tsv":         os.path.basename(tsv_path) if tsv_path else None,
                            "final_value": final_value,
                        }) + "\n")
                except Exception as e:
                    print(f"[MAPs Server] WARN: trajectory save failed: {e}")

            # Restart this same slot for the next episode
            self.close()
            self.episode_count += 1
            self.start()
            new_concise = make_concise_obs(self.obs)

            print(
                f"[MAPs Server] Park {self.slot_index} episode {completed_episode + 1} "
                f"complete. Final value=${final_value}. "
                f"Episode {self.episode_count + 1} started."
            )
            return {
                "episode_complete":     True,
                "park_index":           self.slot_index,
                "completed_episode":    completed_episode,
                "final_step":           final_step,
                "total_reward":         final_total_reward,
                "final_value":          final_value,
                "reward":               float(reward),
                "error":                error,
                "message": (
                    f"Park {self.slot_index} episode {completed_episode + 1} complete! "
                    f"Final value: ${final_value:,} out of a possible $10,000,000. "
                    f"This park slot is restarting from scratch as episode {self.episode_count + 1}. "
                    "Record what worked and what didn't in your strategy artifacts, "
                    "then apply those lessons to beat your previous score!"
                ),
                "new_park_index":       self.slot_index,
                "new_park_observation": new_concise,
            }

        return {
            "park_index":        self.slot_index,
            "episode":           self.episode_count,
            "step":              self.step_count,
            "horizon":           concise.get("horizon"),
            "reward":            float(reward),
            "cumulative_reward": self.total_reward,
            "error":             error,
            "done":              False,
            "observation":       concise,
        }

    def get_obs(self) -> dict:
        """Return the current observation without stepping."""
        return {
            "park_index":  self.slot_index,
            "episode":     self.episode_count,
            "step":        self.step_count,
            "observation": make_concise_obs(self.obs),
            "message":     f"Initial observation for park slot {self.slot_index}. No action taken yet.",
        }

    def close(self):
        if self._game_ctx is not None:
            try:
                self._game_ctx.__exit__(None, None, None)
            except Exception:
                pass
            self._game_ctx = None
            self.game = None

    def save_state(self, path: str) -> dict:
        """Pickle the current park raw_state + counters to ``path``.

        The raw_state is the full simulator state per MAPs' get_raw_state()
        contract; combined with step_count / total_reward / episode_count
        it is enough to round-trip through MCP+node restarts.
        """
        if self.game is None:
            return {"error": f"slot {self.slot_index} has no live park"}
        try:
            raw_state = self.game.get_raw_state()
        except Exception as err:  # noqa: BLE001
            return {"error": f"get_raw_state failed: {err}"}
        payload = {
            "slot_index":    self.slot_index,
            "layout":        self.layout,
            "difficulty":    self.difficulty,
            "max_steps":     self.max_steps,
            "step_count":    self.step_count,
            "total_reward":  self.total_reward,
            "episode_count": self.episode_count,
            "done":          self.done,
            "raw_state":     raw_state,
        }
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(payload, fh)
        return {
            "saved":      True,
            "path":       path,
            "slot_index": self.slot_index,
            "step":       self.step_count,
            "episode":    self.episode_count,
        }

    def load_state(self, path: str) -> dict:
        """Restore park state from a pickle written by save_state.

        Requires this slot to already have a live game (call start() first);
        will POST the raw_state via MAPs' set() to the node backend.
        """
        if not os.path.exists(path):
            return {"error": f"state file not found: {path}"}
        try:
            with open(path, "rb") as fh:
                payload = pickle.load(fh)
        except Exception as err:  # noqa: BLE001
            return {"error": f"unpickle failed: {err}"}
        if self.game is None:
            return {"error": f"slot {self.slot_index} has no live park"}
        raw_state = payload.get("raw_state")
        if not isinstance(raw_state, dict):
            return {"error": "state file has no raw_state dict"}
        try:
            self.obs, _ = self.game.set(raw_state)
        except Exception as err:  # noqa: BLE001
            return {"error": f"set() failed: {err}"}
        self.step_count    = int(payload.get("step_count", 0))
        self.total_reward  = float(payload.get("total_reward", 0.0))
        self.episode_count = int(payload.get("episode_count", 0))
        self.done          = bool(payload.get("done", False))
        print(
            f"[MAPs Server] Park slot {self.slot_index} restored from {path}: "
            f"episode {self.episode_count + 1}, step {self.step_count}, "
            f"cumulative_reward={self.total_reward:.1f}"
        )
        return {
            "loaded":     True,
            "path":       path,
            "slot_index": self.slot_index,
            "step":       self.step_count,
            "episode":    self.episode_count,
        }


# ── MCP server ────────────────────────────────────────────────────────────────

_games: list[GameManager] = []
# Instantiated in main() once host/port are known; tools registered after.
mcp: FastMCP | None = None
# When non-empty, save_state(_state_file_path) is called after every step()
# so the latest simulator state survives MCP/node restarts.
_state_file_path: str = ""


class UserMessage(BaseModel):
    text: str
    agent_tag: str | None = None  # passed by TL runner; ignored here


def world_server(user_message: UserMessage) -> str:
    """
    Submit an action to a specific Mini Amusement Park slot and receive the
    updated park observation.

    The payload must be a JSON object with two fields:
      {"park": <slot_index>, "action": "<MAPs action string>"}

    Example payloads:
      {"park": 0, "action": "wait()"}
      {"park": 2, "action": "place(x=7, y=9, type='ride', subtype='carousel', subclass='yellow', price=4)"}
      {"park": 1, "action": "set_research(research_speed='slow', research_topics=['carousel'])"}

    If "park" is omitted it defaults to slot 0 (backward compatibility).
    Returns JSON with keys: park_index, episode, step, reward, cumulative_reward,
    error, done, observation.
    """
    global _games
    if not _games:
        return json.dumps({"error": "Games not initialized. Server is still starting."})

    payload = user_message.text.strip()
    park_idx = 0
    action_str = payload or "wait()"
    try:
        parsed = json.loads(payload)
        park_idx = int(parsed.get("park", 0))
        action_str = parsed.get("action", "wait()")
    except (json.JSONDecodeError, ValueError, AttributeError):
        # Legacy plain action string — route to park 0
        action_str = payload or "wait()"

    if park_idx < 0 or park_idx >= len(_games):
        return json.dumps({
            "error": f"Invalid park index {park_idx}. Valid range: 0-{len(_games) - 1}."
        })

    result = _games[park_idx].step(action_str)
    if _state_file_path and park_idx == 0:
        _games[park_idx].save_state(_state_file_path)
    return json.dumps(result, indent=2)


class ObserveRequest(BaseModel):
    park: int = 0


def world_observe(request: ObserveRequest) -> str:
    """Return a park's current observation WITHOUT stepping the simulator.

    Lets an external runner seed the initial (step 0) observation before the
    first action, so the first turn can be a real build instead of a throwaway
    wait() used only to fetch state. Same envelope shape as world_server minus
    the step-result fields (reward/done): park_index, episode, step,
    observation, message.
    """
    global _games
    if not _games:
        return json.dumps({"error": "Games not initialized. Server is still starting."})
    park_idx = request.park
    if park_idx < 0 or park_idx >= len(_games):
        return json.dumps({
            "error": f"Invalid park index {park_idx}. Valid range: 0-{len(_games) - 1}."
        })
    return json.dumps(_games[park_idx].get_obs(), indent=2)


# ── Snapshot tools (rollback support for external runners) ───────────────────

class SnapshotRequest(BaseModel):
    park: int = 0
    path: str | None = None  # if omitted, an auto path under _snapshot_dir is used
    agent_tag: str | None = None


class RestoreRequest(BaseModel):
    park: int = 0
    path: str
    agent_tag: str | None = None


_snapshot_dir: str = ""

# When set, the completed-episode trajectory TSV + a park_ids.jsonl id map are
# written here at each episode end (see step()).
_trajectory_dir: str = ""


def snapshot_state(request: SnapshotRequest) -> str:
    """Pickle the current park state to disk so an external runner can roll back later.

    The path is either caller-supplied (request.path) or auto-generated under
    the server's snapshot directory using park slot + step + millis. Returns
    JSON {saved, path, step, total_reward, episode}.
    """
    global _games, _snapshot_dir
    if not _games:
        return json.dumps({"error": "Games not initialized."})
    park_idx = int(request.park)
    if park_idx < 0 or park_idx >= len(_games):
        return json.dumps({
            "error": f"Invalid park index {park_idx}. Valid range: 0-{len(_games) - 1}."
        })

    path = request.path
    if not path:
        if not _snapshot_dir:
            return json.dumps({
                "error": "No path supplied and --snapshot_dir not configured on the MCP server."
            })
        os.makedirs(_snapshot_dir, exist_ok=True)
        gm = _games[park_idx]
        ts_ms = int(time.time() * 1000)
        fname = f"park{park_idx}_step{gm.step_count}_{ts_ms}.pkl"
        path = os.path.join(_snapshot_dir, fname)

    result = _games[park_idx].save_state(path)
    return json.dumps(result, indent=2)


def restore_state(request: RestoreRequest) -> str:
    """Restore a park slot from a snapshot pickle previously written by
    snapshot_state (or by the autosave path).

    Returns JSON envelope from GameManager.load_state, including {loaded, step,
    total_reward, episode, done}.
    """
    global _games
    if not _games:
        return json.dumps({"error": "Games not initialized."})
    park_idx = int(request.park)
    if park_idx < 0 or park_idx >= len(_games):
        return json.dumps({
            "error": f"Invalid park index {park_idx}. Valid range: 0-{len(_games) - 1}."
        })
    if not request.path:
        return json.dumps({"error": "path is required for restore_state."})
    if not os.path.exists(request.path):
        return json.dumps({"error": f"snapshot not found: {request.path}"})

    result = _games[park_idx].load_state(request.path)
    return json.dumps(result, indent=2)


# ── Broadcast helper ──────────────────────────────────────────────────────────

def push_broadcast(callback_url: str, payload: str) -> None:
    """POST a broadcast message to OGW's /incoming listener."""
    envelope = {
        "v":       1,
        "type":    "event",
        "id":      str(uuid.uuid4()),
        "source":  {"agent_tag": None},
        "target":  None,   # None => broadcast to all agents
        "payload": payload,
        "meta":    {},
    }
    try:
        resp = requests.post(callback_url, json=envelope, timeout=5)
        print(f"[MAPs Server] Broadcast to {callback_url}: HTTP {resp.status_code}")
    except Exception as e:
        print(f"[MAPs Server] Failed to broadcast initial obs: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="MCP server for the MAPs benchmark")
    parser.add_argument("--maps_repo_dir", default="../mini_amusement_parks/MAPs",
                        help="Path to the MAPs repo root (must contain map_py/)")
    parser.add_argument("--maps_host",  default="127.0.0.1",
                        help="MAPs Node.js backend host")
    parser.add_argument("--maps_port",  type=int, default=3000,
                        help="MAPs Node.js backend port")
    parser.add_argument("--mcp_host",   default="0.0.0.0",
                        help="Host for this MCP server to bind to")
    parser.add_argument("--mcp_port",   type=int, default=8080,
                        help="Port for this MCP server")
    parser.add_argument("--layout",     default="the_islands",
                        help="MAPs park layout name")
    parser.add_argument("--difficulty", default="medium",
                        help="MAPs difficulty: easy | medium")
    parser.add_argument("--steps",      type=int, default=100,
                        help="Max MAPs steps per episode")
    parser.add_argument("--num_parks",  type=int, default=5,
                        help="Number of park slots running in parallel")
    parser.add_argument("--tl_callback_url", default=None,
                        help=(
                            "OGW /incoming URL for pushing the initial park observations "
                            "to all agents (e.g. http://localhost:9000/incoming). "
                            "If omitted, agents receive the first obs after their "
                            "first external_action call."
                        ))
    parser.add_argument("--state_file", default=None,
                        help=(
                            "Pickle file for persistent slot-0 park state. "
                            "When set, on every step the file is overwritten with "
                            "the latest state. Empty/unset = no autosave. "
                            "Combined with --resume the file is also loaded on startup."
                        ))
    parser.add_argument("--resume", action="store_true",
                        help=(
                            "On startup, load slot 0 from --state_file (if the file "
                            "exists). Default is a fresh park; --resume opts in to "
                            "restoring a prior run."
                        ))
    parser.add_argument("--snapshot_dir", default=None,
                        help=(
                            "Directory where snapshot_state(park=...) saves "
                            "auto-named pickles when the caller doesn't supply "
                            "an explicit path. Required for runner-driven rollback."
                        ))
    parser.add_argument("--trajectory_dir", default=None,
                        help=(
                            "Directory where each completed episode's trajectory "
                            "TSV and a park_ids.jsonl (episode -> park_id map) are "
                            "written. Point this at the run log dir to keep TSVs "
                            "alongside run.ep*.jsonl. Empty/unset = no TSV save."
                        ))
    args = parser.parse_args()

    # Make map_py importable from maps_repo_dir
    maps_repo_abs = os.path.abspath(args.maps_repo_dir)
    if maps_repo_abs not in sys.path:
        sys.path.insert(0, maps_repo_abs)

    global _games, mcp, _state_file_path, _snapshot_dir, _trajectory_dir
    mcp = FastMCP("MAPs Park Server", host=args.mcp_host, port=args.mcp_port)
    mcp.tool()(world_server)
    mcp.tool()(world_observe)
    mcp.tool()(snapshot_state)
    mcp.tool()(restore_state)
    _state_file_path = args.state_file or ""
    _snapshot_dir = args.snapshot_dir or ""
    _trajectory_dir = args.trajectory_dir or ""
    if _trajectory_dir:
        os.makedirs(_trajectory_dir, exist_ok=True)

    print("=" * 60)
    print(f"  MAPs MCP Server  ({args.num_parks} parallel parks)")
    print(f"  Layout: {args.layout}  |  Difficulty: {args.difficulty}")
    print(f"  MAPs repo:    {maps_repo_abs}")
    print(f"  MAPs backend: {args.maps_host}:{args.maps_port}")
    print(f"  MCP endpoint: http://{args.mcp_host}:{args.mcp_port}/mcp")
    print("=" * 60)

    for slot in range(args.num_parks):
        gm = GameManager(
            slot_index=slot,
            maps_host=args.maps_host,
            maps_port=args.maps_port,
            layout=args.layout,
            difficulty=args.difficulty,
            max_steps=args.steps,
        )
        gm.start()
        _games.append(gm)

    # Slot 0 is the only persisted slot — the agent network only uses park 0.
    # Restore only if the user explicitly opted in with --resume.
    if args.resume:
        if not _state_file_path:
            print("[MAPs Server] --resume given but no --state_file configured; ignoring.")
        elif not os.path.exists(_state_file_path):
            print(f"[MAPs Server] --resume given but {_state_file_path} not found; starting fresh.")
        else:
            load_result = _games[0].load_state(_state_file_path)
            if "error" in load_result:
                print(f"[MAPs Server] --resume load failed: {load_result['error']}")
            # else: load_state already prints the success line

    # Push initial observations for all park slots to OGW agents
    if args.tl_callback_url:
        print(f"[MAPs Server] Pushing initial observations for {args.num_parks} parks to OGW agents...")
        for gm in _games:
            initial_payload = json.dumps(gm.get_obs(), indent=2)
            push_broadcast(args.tl_callback_url, initial_payload)

    print(f"[MAPs Server] Starting MCP server on port {args.mcp_port}...")
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
