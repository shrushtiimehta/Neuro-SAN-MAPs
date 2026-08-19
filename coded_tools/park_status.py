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
ParkStatus: structured snapshot of the current park state.

Reads the latest observation envelope from LatestObservation and maps the
real simulator field names to a clean summary:

  - cash (from observation.money)
  - step, park_rating, park_value, cumulative_reward, done
  - entrance, exit: [x, y] positions
  - path_coords: list of {x, y} path tiles (for staff placement)
  - reachable_tiles: from observation.valid_placement_coords — tiles ready for
    placement (already computed by the simulator, no grid scan needed)
  - water_adjacent: free tiles touching water as {x, y, water}, where `water`
    is the excitement bonus (+1 per adjacent water tile, stacking), best first
  - unreachable_tiles: buildable tiles guests can never walk to (capacity only)
  - broken_rides: entries from ride_list where out_of_service=true
  - out_of_service: true if any ride is out of service (park-wide flag)
  - min_uptime: park-wide worst uptime across rides and shops
  - min_cleanliness: park-wide worst tile cleanliness (from observation)
  - placed_rides: observation.rides.ride_list
  - placed_shops: observation.shops.shop_list
  - placed_staff: observation.staff.staff_list
  - available_entities: subtype → [unlocked subclasses] (research tracking)
  - research_speed: current research speed string
  - next_unlock: {subtype, tier, days} ETA of the next subclass unlock, or null
  - guests: aggregate GuestStats — free daily guest signal
  - guest_survey_results: paid survey detail {age_of_results, list_of_results}

As a side effect, writes per-specialist snapshot files to
coded_tools/state/ so each specialist reads only the fields it
needs via state_read(name='status_<domain>').
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.latest_observation import LatestObservation

_STATE_DIR = Path("coded_tools/state")
# The macro writes the full turn-phased plan here at episode start; ParkStatus
# surfaces ONLY the line whose turn-range covers the current step (current_phase)
# so the game-runner never carries the whole checklist per turn.
_EPISODE_CHECKLIST = _STATE_DIR / "episode_checklist.md"
# Matches a checklist line "turns A-B: <goal>" (or "turns A: <goal>").
_PHASE_RE = re.compile(r"turns?\s+(\d+)\s*(?:[-–]\s*(\d+))?\s*:\s*(.+)", re.IGNORECASE)

# Top-level keys written into each specialist's status file.
_SPECIALIST_FIELDS: dict[str, list[str]] = {
    "rides":       ["step", "cash", "park_rating", "park_capacity", "avg_intensity", "placed_rides",
                    "available_entities", "broken_rides", "next_unlock"],
    # +guests: order_quantity is sized off total_guests, and shop `uptime` counts
    # stock-outs only (an unaffordable item never reaches services_attempted), so
    # GuestStats is the manager's only read on real demand.
    "shops":       ["step", "cash", "park_rating", "placed_shops", "available_entities",
                    "guests", "next_unlock"],
    # +daily_profit/horizon: the playbook's two live constraints — "never starve
    # daily operating cash" needs the park's net P&L, not just the cash stock, and
    # "unlock early enough to exploit it" needs the turns left to build with.
    "research":    ["step", "horizon", "cash", "daily_profit", "park_rating", "park_value",
                    "research_speed", "research_topics", "research_operating_cost",
                    "available_entities", "next_unlock"],
    "staff":       ["step", "cash", "park_rating", "out_of_service", "min_uptime", "min_cleanliness",
                    "placed_staff", "available_entities", "next_unlock"],
    "survey":      ["step", "cash", "park_rating", "guests", "guest_survey_results"],
    "layout":      ["step", "park_rating", "reachable_tiles", "water_adjacent", "unreachable_tiles",
                    "path_coords", "placed_rides", "placed_shops", "placed_staff", "entrance", "exit"],
    # +available_entities: FinanceGate reads this slice to price a research run
    # against the tier it will actually unlock next, so the unlock ledger has to
    # be here — it replaced the LLM-supplied `target_tier`.
    # +next_unlock: the coordinator picks the ONE action, so "don't spend the last
    # reachable tile today, a higher tier lands tomorrow" is its call to make, not
    # the proposing specialist's.
    "coordinator": ["step", "horizon", "cash", "park_rating", "park_value", "daily_profit", "park_capacity",
                    "avg_intensity", "research_speed", "current_phase", "available_entities",
                    "placed_staff", "placed_shops", "placed_rides", "next_unlock"],
}

# available_entities lists every buildable subtype across ALL domains; each
# specialist should see only its own. A domain absent here (e.g. research, which
# unlocks everything) keeps the full map.
_DOMAIN_SUBTYPES: dict[str, frozenset[str]] = {
    "rides": frozenset({"carousel", "ferris_wheel", "roller_coaster"}),
    "shops": frozenset({"drink", "food", "specialty"}),
    "staff": frozenset({"janitor", "mechanic", "specialist"}),
}

# Per-specialist entity field pruning: (specialist, list_key) → fields to keep.
# None means keep all fields. Reduces token cost for consumers that don't need
# full operational stats — e.g. FinanceGate only needs subtype+subclass.
# Research points bought per day, per speed (shared/config.yaml research.speed_progress).
_SPEED_POINTS: dict[str, int] = {"none": 0, "slow": 25, "medium": 50, "fast": 100}

_IDENTITY = ["subtype", "subclass"]
_POSITION = ["subtype", "subclass", "x", "y"]
# Position + siting signals shared by layout's ride and shop lists. Layout evicts
# on tier first (read off `subclass`) and breaks ties on the popularity counter —
# guests_entertained for rides, guests_served for shops (the sim names them
# differently per type, and each list carries only its own).
# +reachable: whether a guest can walk to this tile — a stranded asset earns $0
# forever and no usage figure can say so, since a fresh build reads 0 too.
_PERF = _POSITION + ["reachable", "cleanliness"]
_ENTITY_FIELDS: dict[tuple[str, str], list[str]] = {
    # Rides manager cares about build/upgrade/pricing economics, not maintenance
    # (uptime/cleanliness/out_of_service) — those are staff/layout concerns.
    # avg_guests_per_operation pairs with capacity: a ride waits capacity*2 ticks
    # for its queue to fill, so the gap between the two is the oversized-ride tell.
    ("rides",       "placed_rides"):  _POSITION + ["ticket_price", "capacity",
                                                   "avg_guests_per_operation", "intensity",
                                                   "excitement", "guests_entertained", "avg_wait_time",
                                                   "reachable"],
    # Shops manager drops number_of_restocks (only ever nonzero once staff hires
    # a blue stocker — a staffing outcome the shops manager has no lever on).
    ("shops",       "placed_shops"):  _POSITION + ["item_price", "item_cost", "uptime", "order_quantity",
                                                   "inventory", "cleanliness",
                                                   "guests_served", "out_of_service",
                                                   "reachable"],
    # A broken ride needs identity + how bad it is; passing the full ride record
    # would smuggle raw revenue_generated/operating_cost in.
    ("rides",       "broken_rides"):  _POSITION + ["uptime"],
    # +operating_cost so FinanceGate can charge the park's REAL daily burn against
    # a proposal (the sim's own realized figure: cost_per_operation x times_operated
    # for a ride, order_quantity x item_cost for a shop) instead of counting only
    # staff salaries + research. Identity alone left the "1-day buffer" rule blind
    # to the two largest recurring costs in the park.
    ("coordinator", "placed_rides"):  _IDENTITY + ["operating_cost"],
    ("coordinator", "placed_shops"):  _IDENTITY + ["operating_cost"],
    ("coordinator", "placed_staff"):  _IDENTITY,
    ("layout",      "placed_rides"):  _PERF + ["capacity", "excitement", "guests_entertained",
                                               "uptime", "avg_wait_time"],
    # guests_served is the shop's equivalent of guests_entertained — the shop
    # record has no guests_entertained, so that tie-break never fired.
    ("layout",      "placed_shops"):  _PERF + ["guests_served"],
    # +success_metric_value so layout can tie-break which duplicate staff to remove.
    ("layout",      "placed_staff"):  _POSITION + ["success_metric_value"],
    # staff keeps ALL fields on placed_staff (salary, operating_cost, success_metric*,
    # tiles_traversed) so the manager can judge which hire to dismiss.
}


class ParkStatus(CodedTool):
    """Return a structured park snapshot from the latest observation envelope."""

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        park = str(args.get("park") or "0")

        window = await LatestObservation().async_invoke(
            {"mode": "read", "park": park}, sly_data
        )
        if not isinstance(window, dict):
            return {"error": f"LatestObservation returned unexpected type: {type(window).__name__}"}
        if window.get("window_size", 0) == 0:
            return {
                "error": "No observation stored yet — first step of the episode. "
                         "Proceed with placing a ride or other productive action."
            }

        envelope = window.get("latest") or {}
        obs = envelope.get("observation") or {}

        snapshot = {
            "episode":            envelope.get("episode"),
            "cash":               obs.get("money"),
            "step":               obs.get("step") or envelope.get("step"),
            # Runway. Every "does this repay before the run ends?" rule (research
            # spend, ride payback) needs horizon - step; without it `step` alone
            # says nothing about how much episode is left.
            "horizon":            obs.get("horizon"),
            "park_rating":        obs.get("park_rating"),
            "park_value":         obs.get("value"),
            "daily_profit":       obs.get("profit"),
            "park_capacity":      (obs.get("rides") or {}).get("total_capacity"),
            "avg_intensity":      (obs.get("rides") or {}).get("avg_intensity"),
            "cumulative_reward":  envelope.get("cumulative_reward"),
            "done":               envelope.get("done", False),
            "entrance":           obs.get("entrance"),
            "exit":               obs.get("exit"),
            "path_coords":        self._to_xy_list(obs.get("path_coords") or []),
            "reachable_tiles":         self._to_xy_list(obs.get("valid_placement_coords") or []),
            # Passed through, NOT _to_xy_list — that would strip the `water`
            # bonus count and the highest-first ordering the server sorted by.
            "water_adjacent":     obs.get("water_adjacent") or [],
            "unreachable_tiles":  self._to_xy_list(obs.get("unreachable_tiles") or []),
            "broken_rides":       self._broken_rides(obs),
            "out_of_service":     bool(self._broken_rides(obs)),
            "min_uptime":         self._min_uptime(obs),
            "min_cleanliness":    obs.get("min_cleanliness"),
            "placed_rides":       self._section_list(obs, "rides", "ride_list"),
            "placed_shops":       self._section_list(obs, "shops", "shop_list"),
            "placed_staff":       self._section_list(obs, "staff", "staff_list"),
            "available_entities": obs.get("available_entities") or {},
            "research_speed":     obs.get("research_speed"),
            "research_topics":    obs.get("research_topics") or [],
            "research_operating_cost": obs.get("research_operating_cost"),
            "next_unlock":        self._next_unlock(obs),
            "guests":             obs.get("guests") or {},
            "guest_survey_results": obs.get("guest_survey_results") or {},
            "current_phase":      self._current_phase(obs.get("step") or envelope.get("step")),
        }

        self._write_specialist_snapshots(snapshot)
        return snapshot

    def _current_phase(self, step: Any) -> str | None:
        """The single checklist line whose 'turns A-B' range covers `step`.

        The macro owns the full plan (episode_checklist.md); we surface only the
        relevant line so park_director forwards one phase per turn instead of the
        whole checklist. Step below the first range -> first line; above the last
        -> last line. Returns None if there is no (parseable) checklist.
        """
        try:
            s = int(step)
        except (TypeError, ValueError):
            return None
        if not _EPISODE_CHECKLIST.exists():
            return None
        try:
            lines = _EPISODE_CHECKLIST.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        phases: list[tuple[int, int, str]] = []
        for ln in lines:
            m = _PHASE_RE.search(ln)
            if not m:
                continue
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            phases.append((lo, hi, ln.strip()))
        if not phases:
            return None
        for lo, hi, full in phases:
            if lo <= s <= hi:
                return full
        phases.sort(key=lambda p: p[0])
        return phases[0][2] if s < phases[0][0] else phases[-1][2]

    def _write_specialist_snapshots(self, snapshot: dict[str, Any]) -> None:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        for specialist, fields in _SPECIALIST_FIELDS.items():
            data: dict[str, Any] = {}
            for k in fields:
                if k not in snapshot:
                    continue
                if k == "available_entities":
                    allowed = _DOMAIN_SUBTYPES.get(specialist)
                    data[k] = (
                        {s: v for s, v in snapshot[k].items() if s in allowed}
                        if allowed and isinstance(snapshot[k], dict) else snapshot[k]
                    )
                    continue
                keep = _ENTITY_FIELDS.get((specialist, k))
                if keep is not None and isinstance(snapshot[k], list):
                    data[k] = [
                        {f: e[f] for f in keep if f in e}
                        for e in snapshot[k]
                        if isinstance(e, dict)
                    ]
                else:
                    data[k] = snapshot[k]
            path = _STATE_DIR / f"status_{specialist}.json"
            path.write_text(json.dumps(data, indent=2))

    def _to_xy_list(self, coords: list) -> list[dict[str, int]]:
        result: list[dict[str, int]] = []
        for c in coords:
            if isinstance(c, (list, tuple)) and len(c) >= 2:
                result.append({"x": int(c[0]), "y": int(c[1])})
            elif isinstance(c, dict) and "x" in c and "y" in c:
                result.append({"x": int(c["x"]), "y": int(c["y"])})
        return result

    def _section_list(self, obs: dict[str, Any], section: str, key: str) -> list:
        return (obs.get(section) or {}).get(key) or []

    def _broken_rides(self, obs: dict[str, Any]) -> list:
        ride_list = self._section_list(obs, "rides", "ride_list")
        return [r for r in ride_list if r.get("out_of_service")]

    def _next_unlock(self, obs: dict[str, Any]) -> dict[str, Any] | None:
        """Exact {subtype, tier, days} until the next subclass unlocks, so
        rides/shops/staff can reserve cash and a free tile BEFORE it lands.

        Reads `research_progress` — the sim's own live counters, forwarded by
        maps_mcp_server. `points_remaining` is what is actually left on the tier
        the sim is grinding right now, so this is arithmetic, not the estimate
        the old version reconstructed from the days-since-unlock counters.

        None when research is off or every listed topic is fully unlocked (the
        sim leaves current_entity undefined in both cases).
        """
        progress = obs.get("research_progress")
        if not isinstance(progress, dict):
            return None
        per_day = _SPEED_POINTS.get(obs.get("research_speed") or "none", 0)
        remaining = progress.get("points_remaining")
        if not per_day or not isinstance(remaining, (int, float)):
            return None
        entity, tier = progress.get("current_entity"), progress.get("current_color")

        # The queue behind the head. Research runs round-robin, so every topic
        # still missing THIS tier reaches it before any moves on to the next --
        # a manager whose domain is second in line still needs to prepare.
        # Rotated to start at the cursor, so the order is the sim's own.
        unlocked = obs.get("available_entities") or {}
        topics = [t for t in (obs.get("research_topics") or unlocked) if t in unlocked]
        queue = [t for t in topics if tier not in (unlocked.get(t) or [])]
        if entity in queue:
            cut = queue.index(entity)
            queue = queue[cut:] + queue[:cut]

        return {
            "subtype":  entity,
            "tier":     tier,
            "days":     math.ceil(remaining / per_day),
            "subtypes": queue or [entity],
        }

    def _min_uptime(self, obs: dict[str, Any]) -> float | None:
        """Park-wide worst uptime across rides and shops (the sim reports these
        per-section). None if neither section is present."""
        vals = [
            (obs.get(sec) or {}).get("min_uptime")
            for sec in ("rides", "shops")
        ]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None
