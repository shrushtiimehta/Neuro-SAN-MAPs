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
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.maps_park.latest_observation import LatestObservation


class ParkStatus(CodedTool):
    """Return a structured park snapshot from the latest observation envelope."""

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        park = str(args.get("park", "0"))

        window = await LatestObservation().async_invoke(
            {"mode": "read", "park": park}, sly_data
        )
        if not isinstance(window, dict):
            return {"error": f"LatestObservation returned unexpected type: {type(window).__name__}"}
        if window.get("window_size", 0) == 0:
            return {
                "error": "No observation stored yet. The park_director calls wait() on the "
                         "first turn to fetch the initial state — call ParkStatus after that."
            }

        envelope = window.get("latest") or {}
        obs = envelope.get("observation") or {}

        return {
            "cash":              obs.get("money"),
            "step":              obs.get("step") or envelope.get("step"),
            "park_rating":       obs.get("park_rating"),
            "park_value":        obs.get("value"),
            "cumulative_reward": envelope.get("cumulative_reward"),
            "done":              envelope.get("done", False),
            "entrance":          obs.get("entrance"),
            "exit":              obs.get("exit"),
            "path_coords":       self._to_xy_list(obs.get("path_coords") or []),
            "free_tiles":        self._to_xy_list(obs.get("valid_placement_coords") or []),
            "broken_rides":      self._broken_rides(obs),
            "placed_rides":      self._section_list(obs, "rides",  "ride_list"),
            "placed_shops":      self._section_list(obs, "shops",  "shop_list"),
            "placed_staff":      self._section_list(obs, "staff",  "staff_list"),
            "available_entities": obs.get("available_entities") or {},
            "research_speed":    obs.get("research_speed"),
        }

    def _to_xy_list(self, coords: list) -> list[dict[str, int]]:
        """Convert [[x,y], ...] or [{x,y}, ...] to [{x,y}, ...] dicts."""
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
