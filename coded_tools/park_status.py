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
  - free_tiles: from observation.valid_placement_coords — tiles ready for
    placement (already computed by the simulator, no grid scan needed)
  - broken_rides: entries from ride_list where out_of_service=true
  - placed_rides: observation.rides.ride_list
  - placed_shops: observation.shops.shop_list
  - placed_staff: observation.staff.staff_list
  - available_entities: subtype → [unlocked subclasses] (research tracking)
  - research_speed: current research speed string
  - guests: aggregate GuestStats — free daily guest signal
  - guest_survey_results: paid survey detail {age_of_results, list_of_results}

As a side effect, writes per-specialist snapshot files to
coded_tools/state/ so each specialist reads only the fields it
needs via state_read(name='status_<domain>').
"""

from __future__ import annotations

import json
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
    "rides":       ["step", "cash", "park_rating", "placed_rides", "available_entities", "broken_rides"],
    "shops":       ["step", "cash", "park_rating", "placed_shops", "available_entities"],
    "research":    ["step", "cash", "park_rating", "research_speed", "research_topics", "research_operating_cost", "available_entities"],
    "staff":       ["step", "cash", "park_rating", "placed_staff", "placed_rides", "broken_rides"],
    "survey":      ["step", "cash", "park_rating", "guests", "guest_survey_results"],
    "layout":      ["step", "park_rating", "free_tiles", "path_coords", "placed_rides", "placed_shops",
                    "placed_staff", "entrance", "exit"],
    "coordinator": ["step", "cash", "park_rating", "park_value", "research_speed", "current_phase",
                    "placed_staff", "placed_shops", "placed_rides"],
}

# Per-specialist entity field pruning: (specialist, list_key) → fields to keep.
# None means keep all fields. Reduces token cost for consumers that don't need
# full operational stats — e.g. FinanceGate only needs subtype+subclass.
_IDENTITY = ["subtype", "subclass"]
_POSITION = ["subtype", "subclass", "x", "y"]
# Position + earnings, so layout can rank placed rides/shops by net contribution
# (revenue_generated - operating_cost) and pick the worst performer to remove.
_PERF = _POSITION + ["revenue_generated", "operating_cost", "guests_entertained"]
_ENTITY_FIELDS: dict[tuple[str, str], list[str]] = {
    ("coordinator", "placed_rides"):  _IDENTITY,
    ("coordinator", "placed_shops"):  _IDENTITY,
    ("coordinator", "placed_staff"):  _IDENTITY,
    ("layout",      "placed_rides"):  _PERF,
    ("layout",      "placed_shops"):  _PERF,
    ("layout",      "placed_staff"):  _POSITION,
    ("staff",       "placed_rides"):  _POSITION + ["out_of_service"],
    ("staff",       "broken_rides"):  _POSITION,
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
            "park_rating":        obs.get("park_rating"),
            "park_value":         obs.get("value"),
            "cumulative_reward":  envelope.get("cumulative_reward"),
            "done":               envelope.get("done", False),
            "entrance":           obs.get("entrance"),
            "exit":               obs.get("exit"),
            "path_coords":        self._to_xy_list(obs.get("path_coords") or []),
            "free_tiles":         self._to_xy_list(obs.get("valid_placement_coords") or []),
            "broken_rides":       self._broken_rides(obs),
            "placed_rides":       self._section_list(obs, "rides", "ride_list"),
            "placed_shops":       self._section_list(obs, "shops", "shop_list"),
            "placed_staff":       self._section_list(obs, "staff", "staff_list"),
            "available_entities": obs.get("available_entities") or {},
            "research_speed":     obs.get("research_speed"),
            "research_topics":    obs.get("research_topics") or [],
            "research_operating_cost": obs.get("research_operating_cost"),
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
