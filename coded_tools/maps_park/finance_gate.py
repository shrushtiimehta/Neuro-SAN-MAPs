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
FinanceGate: deterministic budget gate for MAPs park actions.

Replaces the finance_controller LLM agent with arithmetic that is always
correct. Rules applied per proposal, in priority order:

  1. action='wait'                        → always APPROVE
  2. action='remove'                      → always APPROVE (recovers 66%)
  3. specialty/red (Billboard)            → REJECT unless has_food_or_atm=True
                                            (Billboard earns $0 directly)
  4. action='place', type='ride'          → REJECT if days_remaining <
                                            BREAK_EVEN_DAYS[subtype][subclass]
                                            (computed from economics files at
                                            5 ops/day assumption)
  5. is_research=True                     → APPROVE only when ALL of:
       (a) has_profitable_ride=True
       (b) days_remaining >= 30
       (c) cash >= research_daily_cost * research_days + recurring_daily
  6. Everything else                      → APPROVE when:
       cash - one_time_cost >= recurring_daily (keep 1-day buffer)

Break-even days are derived from rides_economics.yaml at 5 ops/day
(moderate-park assumption). Values:
  carousel:      yellow=3  blue=4   green=7  red=9
  ferris_wheel:  yellow=3  blue=13  green=19 red=20
  roller_coaster:yellow=7  blue=17  green=14 red=20
"""

from __future__ import annotations

import json
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


class FinanceGate(CodedTool):
    """Approve or reject a list of proposed MAPs actions based on budget rules."""

    ALWAYS_APPROVE_ACTIONS: ClassVar[frozenset[str]] = frozenset({"wait", "remove"})

    # Break-even days per (subtype, subclass) at 5 ops/day.
    # Derived from rides_economics.yaml:
    #   break_even_ops = ceil(building_cost / (max_ticket_price * capacity - cost_per_operation))
    #   break_even_days = ceil(break_even_ops / 5)
    BREAK_EVEN_DAYS: ClassVar[dict[str, dict[str, int]]] = {
        "carousel":       {"yellow": 3,  "blue": 4,  "green": 7,  "red": 9},
        "ferris_wheel":   {"yellow": 3,  "blue": 13, "green": 19, "red": 20},
        "roller_coaster": {"yellow": 7,  "blue": 17, "green": 14, "red": 20},
    }

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        cash = self._int(args.get("cash", 0))
        step = self._int(args.get("step", 0))
        horizon = self._int(args.get("horizon", 100))
        recurring_daily = self._int(args.get("recurring_daily", 0))
        raw_proposals = args.get("proposals") or []
        if isinstance(raw_proposals, str):
            try:
                raw_proposals = json.loads(raw_proposals)
            except json.JSONDecodeError:
                raw_proposals = []
        proposals = raw_proposals if isinstance(raw_proposals, list) else []

        days_remaining = max(0, horizon - step)
        results: list[dict[str, Any]] = []

        for proposal in proposals:
            label = str(proposal.get("label", ""))
            action = str(proposal.get("action", "")).lower()
            entity_type = str(proposal.get("type", "")).lower()
            subtype = str(proposal.get("subtype", "")).lower()
            subclass = str(proposal.get("subclass", "")).lower()
            one_time_cost = self._int(proposal.get("one_time_cost", 0))
            is_research = bool(proposal.get("is_research", False))
            research_daily_cost = self._int(proposal.get("research_daily_cost", 0))
            research_days = self._int(proposal.get("research_days", 0))
            has_food_or_atm = bool(proposal.get("has_food_or_atm", False))
            has_profitable_ride = bool(proposal.get("has_profitable_ride", False))

            approved, reason = self._evaluate(
                cash=cash,
                days_remaining=days_remaining,
                recurring_daily=recurring_daily,
                action=action,
                entity_type=entity_type,
                subtype=subtype,
                subclass=subclass,
                one_time_cost=one_time_cost,
                is_research=is_research,
                research_daily_cost=research_daily_cost,
                research_days=research_days,
                has_food_or_atm=has_food_or_atm,
                has_profitable_ride=has_profitable_ride,
            )
            results.append({"label": label, "approved": approved, "reason": reason})

        return {
            "results": results,
            "cash": cash,
            "recurring_daily": recurring_daily,
            "days_remaining": days_remaining,
        }

    def _evaluate(
        self,
        cash: int,
        days_remaining: int,
        recurring_daily: int,
        action: str,
        entity_type: str,
        subtype: str,
        subclass: str,
        one_time_cost: int,
        is_research: bool,
        research_daily_cost: int,
        research_days: int,
        has_food_or_atm: bool,
        has_profitable_ride: bool,
    ) -> tuple[bool, str]:
        # Rule 1 — wait: free, always go ahead
        if action == "wait":
            return True, "always approved"

        # Rule 2 — remove: recovers 66% of build cost, always beneficial
        if action == "remove":
            return True, "always approved: sell recovers 66% of build cost"

        # Rule 3 — Billboard (specialty/red): earns $0 directly
        if action == "place" and subtype == "specialty" and subclass == "red":
            if not has_food_or_atm:
                return False, (
                    "Billboard (specialty/red) earns $0 direct revenue; "
                    "reject until food/ATM shops are in place to capture demand"
                )

        # Rule 4 — ride break-even: too late in episode to recoup build cost
        if action == "place" and (entity_type == "ride" or subtype in self.BREAK_EVEN_DAYS):
            be_days = self.BREAK_EVEN_DAYS.get(subtype, {}).get(subclass)
            if be_days is not None and days_remaining < be_days:
                return False, (
                    f"{subtype}/{subclass} needs ~{be_days} days to break even "
                    f"but only {days_remaining} steps remain"
                )

        # Rule 5 — research: capital investment, strict approval criteria
        if is_research:
            if not has_profitable_ride:
                return False, (
                    "research requires at least one profitable ride first "
                    "(confirmed revenue > operating cost)"
                )
            if days_remaining < 30:
                return False, (
                    f"only {days_remaining} steps remain; "
                    "need 30+ for research to pay back in park value"
                )
            total_needed = research_daily_cost * research_days + recurring_daily
            if cash < total_needed:
                return False, (
                    f"need ${total_needed} (research run + 1-day buffer), have ${cash}"
                )
            return True, (
                f"research approved: {days_remaining} steps remain, "
                f"cash ${cash} covers full duration"
            )

        # Rule 6 — general cash sufficiency: keep at least 1 day of recurring costs
        cash_after = cash - one_time_cost
        if cash_after < recurring_daily:
            return False, (
                f"cash after spend ${cash_after} < 1-day recurring ${recurring_daily}"
            )
        return True, f"cash after spend ${cash_after} >= 1-day buffer ${recurring_daily}"

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return 0
