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
RecurringDaily: deterministic per-day recurring-cost calculator.

Replaces the LLM-side arithmetic in strategy_coordinator step 3 where it
sums every staff salary and adds the research speed cost. That sum is the
denominator FinanceGate uses for every approve/reject decision, so a
hallucinated number cascades. This tool reads the operator-managed
economics files directly and returns the exact integer.

Inputs (passed by the LLM):
  - placed_staff:   list of {subtype, subclass, ...} (status.placed_staff)
  - research_speed: one of {none, slow, medium, fast} (status.research_speed)

Output:
  {
    "recurring_daily":    <int total>,
    "staff_breakdown":    [{"subtype", "subclass", "salary"}, ...],
    "staff_subtotal":     <int>,
    "research_speed":     <echoed>,
    "research_speed_cost": <int>,
  }
"""

from __future__ import annotations

import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


_STAFF_ECONOMICS_PATH = "coded_tools/maps_park/config_files/staff_economics.md"
_RESEARCH_ECONOMICS_PATH = "coded_tools/maps_park/config_files/research_economics.md"


class RecurringDaily(CodedTool):
    """Sum staff salaries + research speed cost into a single recurring_daily int."""

    VALID_SPEEDS: ClassVar[frozenset[str]] = frozenset({"none", "slow", "medium", "fast"})

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: dict with keys
            - ``placed_staff`` (list[dict], required): each dict has
              ``subtype`` and ``subclass`` (extra keys ignored).
            - ``research_speed`` (str, required): one of
              ``none``, ``slow``, ``medium``, ``fast``.
        :param sly_data: ignored.
        :return: dict with ``recurring_daily``, breakdown, and the
                 research_speed_cost — or ``"ERROR: ..."`` string.
        """
        del sly_data

        placed_staff = args.get("placed_staff")
        if not isinstance(placed_staff, list):
            return f"ERROR: invalid_input: placed_staff must be a list, got {type(placed_staff).__name__}"

        research_speed = str(args.get("research_speed", "none")).lower().strip()
        if research_speed not in self.VALID_SPEEDS:
            return (
                f"ERROR: invalid_input: research_speed must be one of "
                f"{sorted(self.VALID_SPEEDS)}, got {research_speed!r}"
            )

        salaries = self._load_staff_salaries()
        if isinstance(salaries, str):  # error path
            return salaries
        speed_costs = self._load_research_speed_costs()
        if isinstance(speed_costs, str):
            return speed_costs

        staff_subtotal = 0
        unknown: list[str] = []
        for entry in placed_staff:
            if not isinstance(entry, dict):
                continue
            subtype = str(entry.get("subtype", "")).lower().strip()
            subclass = str(entry.get("subclass", "")).lower().strip()
            salary = salaries.get((subtype, subclass))
            if salary is None:
                unknown.append(f"{subtype}/{subclass}")
                continue
            staff_subtotal += salary

        research_speed_cost = speed_costs.get(research_speed, 0)
        out: dict[str, Any] = {"recurring_daily": staff_subtotal + research_speed_cost}
        # Surface unknown (subtype, subclass) entries only if they exist —
        # silence on success keeps token count minimal.
        if unknown:
            out["unknown_staff"] = unknown
        return out

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    def _load_staff_salaries(self) -> dict[tuple[str, str], int] | str:
        """Return {(subtype, subclass): salary} parsed from staff_economics.md."""
        if not os.path.exists(_STAFF_ECONOMICS_PATH):
            return f"ERROR: file_not_found: {_STAFF_ECONOMICS_PATH}"
        # staff_economics is sectioned: '## <subtype>/<subclass>' headers
        # followed by '<field>: <value>' lines; grab each section's salary.
        salaries: dict[tuple[str, str], int] = {}
        try:
            cur: tuple[str, str] | None = None
            with open(_STAFF_ECONOMICS_PATH, encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if s.startswith("## ") and "/" in s:
                        subtype, _, subclass = s[3:].partition("/")
                        cur = (subtype.strip().lower(), subclass.strip().lower())
                    elif cur and s.startswith("salary:"):
                        try:
                            salaries[cur] = int(s.split(":", 1)[1].strip())
                        except ValueError:
                            pass
        except OSError as err:
            return f"ERROR: could_not_read: {_STAFF_ECONOMICS_PATH}: {err}"
        if not salaries:
            return f"ERROR: malformed: no salary lines found in {_STAFF_ECONOMICS_PATH}"
        return salaries

    def _load_research_speed_costs(self) -> dict[str, int] | str:
        """Return {speed: cost} parsed from research_economics.md."""
        if not os.path.exists(_RESEARCH_ECONOMICS_PATH):
            return f"ERROR: file_not_found: {_RESEARCH_ECONOMICS_PATH}"
        # research_economics is a markdown table with header
        # '| speed | speed_progress | speed_cost |'; pull the speed_cost column.
        costs: dict[str, int] = {}
        try:
            header: list[str] | None = None
            with open(_RESEARCH_ECONOMICS_PATH, encoding="utf-8") as fh:
                for line in fh:
                    s = line.strip()
                    if not s.startswith("|"):
                        header = None
                        continue
                    cells = [c.strip() for c in s.strip("|").split("|")]
                    if all(set(c) <= set("-: ") for c in cells):
                        continue
                    if header is None:
                        header = [c.lower() for c in cells]
                        continue
                    if header[0] == "speed" and "speed_cost" in header:
                        try:
                            costs[cells[0].lower()] = int(cells[header.index("speed_cost")])
                        except (ValueError, IndexError):
                            pass
        except OSError as err:
            return f"ERROR: could_not_read: {_RESEARCH_ECONOMICS_PATH}: {err}"
        if "none" not in costs:
            costs["none"] = 0
        return costs
