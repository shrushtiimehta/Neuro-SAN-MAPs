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
SpecialistSnapshots: writes per-specialist status slices from the full ParkStatus output.

Called once per turn (by parkstatus_reader, right after ParkStatus). Splits the full
snapshot into five lean files so each specialist reads only what it needs:

  state/status_rides.json    -> rides_manager
  state/status_shops.json    -> shops_manager
  state/status_research.json -> research_lead
  state/status_staff.json    -> staffing_manager
  state/status_layout.json   -> park_layout_planner

Each file is mapped in state_read's name_map so specialists use
state_read(name='status_rides') etc. without knowing the path.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

_STATE_DIR = Path("coded_tools/maps_park/state")

# Fields each specialist actually needs — everything else is omitted.
_SPECIALIST_FIELDS: dict[str, list[str]] = {
    "rides":    ["step", "cash", "placed_rides", "available_entities", "broken_rides"],
    "shops":    ["step", "cash", "placed_shops", "available_entities"],
    "research": ["step", "cash", "research_speed", "available_entities"],
    "staff":    ["step", "cash", "placed_staff", "placed_rides", "broken_rides"],
    "layout":   ["free_tiles", "path_coords", "placed_rides", "placed_shops",
                 "placed_staff", "entrance", "exit"],
}


class SpecialistSnapshots(CodedTool):
    """Split a full ParkStatus snapshot into per-specialist files."""

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any]:
        status: dict[str, Any] = args.get("status") or {}
        if not status:
            return {"error": "No status provided. Pass the full ParkStatus output as 'status'."}

        _STATE_DIR.mkdir(parents=True, exist_ok=True)

        written: list[str] = []
        for specialist, fields in _SPECIALIST_FIELDS.items():
            snapshot = {k: status[k] for k in fields if k in status}
            path = _STATE_DIR / f"status_{specialist}.json"
            path.write_text(json.dumps(snapshot, indent=2))
            written.append(f"status_{specialist}.json")

        return {"written": written, "specialists": list(_SPECIALIST_FIELDS.keys())}
