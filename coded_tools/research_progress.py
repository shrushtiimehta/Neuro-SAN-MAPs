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
"""Canonical, user-facing names for the simulator's research cursor."""

from __future__ import annotations

import math
from typing import Any


class ResearchProgress:
    """Normalize simulator research progress for user-facing output."""

    _POINTS_PER_TURN = {"slow": 25, "medium": 50, "fast": 100}

    @staticmethod
    def normalize_research_progress(value: Any, research_speed: Any = None) -> dict[str, Any] | None:
        """Return exact progress with clear names, accepting legacy cache keys."""
        if str(research_speed or "").lower() == "none":
            return None
        if not isinstance(value, dict) or not value:
            return None
        subtype = value.get("target_subtype", value.get("current_entity"))
        tier = value.get("target_tier", value.get("current_color"))
        turns = value.get("turns_remaining")
        if turns is None:
            turns = ResearchProgress.turns_remaining(value.get("points_remaining"), research_speed)
        if subtype is None and tier is None and turns is None:
            return None
        return {
            "target_subtype": subtype,
            "target_tier": tier,
            "turns_remaining": turns,
        }

    @staticmethod
    def turns_remaining(points: Any, research_speed: Any) -> int | None:
        """Convert remaining research points into turns at the active speed."""
        per_turn = ResearchProgress._POINTS_PER_TURN.get(str(research_speed or "").lower())
        if isinstance(points, (int, float)) and per_turn:
            return math.ceil(points / per_turn)
        return None


# Keep the established function API while the implementation lives in one class.
normalize_research_progress = ResearchProgress.normalize_research_progress
