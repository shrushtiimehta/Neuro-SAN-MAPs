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
FinanceGate: deterministic budget gate + proposal builder for MAPs park
actions.

Two responsibilities, both moved here from the LLM:
  1. ENRICH each raw specialist proposal with derived fields the LLM
     used to compute by hand: one_time_cost (looked up from economics
     files), is_research, has_food_or_atm (scanned from placed_shops),
     has_profitable_ride (scanned from placed_rides), research_days
     (ceil division), and an auto-generated label.
  2. EVALUATE each enriched proposal against deterministic rules and
     return approve/reject + the enriched proposal.

Rules applied per proposal, in priority order:

  1. action='wait'                        → always APPROVE
  2. action='remove'                      → always APPROVE (recovers 66%),
       EXCEPT an upgrade-intent remove (carries upgrade_to_subclass): approve
       only if the replacement ride clears Rule 4's break-even AND fits cash
       after the 66% refund — so we never strand a plot by tearing out a
       yellow we can't actually replace.
  3. specialty/red (Billboard)            → REJECT unless has_food_or_atm=True
                                            (Billboard earns $0 directly)
  4. action='place', type='ride'          → REJECT if days_remaining <
                                            BREAK_EVEN_DAYS[subtype][subclass]
                                            (computed from economics files at
                                            5 ops/day assumption)
  5. is_research=True                     → APPROVE only when ALL of:
       (a) has_profitable_ride=True
       (b) days_remaining >= research_days + POST_UNLOCK_MIN_DAYS
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
import math
import os
import re
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


_RIDES_ECONOMICS_PATH = "coded_tools/maps_park/config_files/rides_economics.md"
_SHOPS_ECONOMICS_PATH = "coded_tools/maps_park/config_files/shops_economics.md"
_STAFF_ECONOMICS_PATH = "coded_tools/maps_park/config_files/staff_economics.md"
_RESEARCH_ECONOMICS_PATH = "coded_tools/maps_park/config_files/research_economics.md"


_TIER_RE = re.compile(r"^(rides|shops|staff)\s+(\S+)\s+(\S+)\s+(\S+):\s*(.+)\s*$")  # legacy fallback


def _coerce(raw: str) -> Any:
    """int -> float -> stripped string."""
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw.strip().strip('"')


def _read_lookup_lines(path: str, domain: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Parse a rides/shops/staff economics file into
    {(domain, subtype, subclass): {field: value}}.

    Accepts three on-disk formats (uniform-field domains use a table;
    variable-field domains use sections; legacy kept for safety):
      - markdown table: header '| subtype | subclass | <field>... |',
        a '|---|' separator, one '| ... |' row per subclass;
      - sectioned:      a '## <subtype>/<subclass>' header followed by
        '<field>: <value>' lines (global '<key>: <value>' lines that
        appear before any section header are ignored);
      - legacy lines:   '<domain> <subtype> <subclass> <field>: <value>'.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not os.path.exists(path):
        return out
    header: list[str] | None = None
    cur_key: tuple[str, str, str] | None = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            if s.startswith("|"):  # table row
                cells = [c.strip() for c in s.strip("|").split("|")]
                if all(set(c) <= set("-: ") for c in cells):  # separator row
                    continue
                if header is None:
                    header = [c.lower() for c in cells]
                    continue
                row = dict(zip(header, cells))
                subtype = row.get("subtype", "").lower()
                subclass = row.get("subclass", "").lower()
                if not subtype or not subclass:
                    continue
                entry = out.setdefault((domain, subtype, subclass), {})
                for col, val in row.items():
                    if col not in ("subtype", "subclass") and val != "":
                        entry[col] = _coerce(val)
                continue
            if s.startswith("## ") and "/" in s:  # section header
                subtype, _, subclass = s[3:].partition("/")
                cur_key = (domain, subtype.strip().lower(), subclass.strip().lower())
                out.setdefault(cur_key, {})
                continue
            m = _TIER_RE.match(s)  # legacy line
            if m:
                d, subtype, subclass, field, raw = m.groups()
                out.setdefault((d, subtype.lower(), subclass.lower()), {})[field] = _coerce(raw)
                continue
            if cur_key and not s.startswith("#") and ":" in s:  # sectioned field line
                field, _, raw = s.partition(":")
                field = field.strip()
                if field and " " not in field:
                    out[cur_key][field] = _coerce(raw.strip())
    return out


def _read_research_lines(path: str) -> dict[tuple[str, str], Any]:
    """Parse research_economics markdown tables into {(field, key): value}.

    Each table's FIRST column is the key dimension (speed or tier) and the
    remaining columns are fields, so a row maps to one entry per field:
    e.g. '| slow | 25 | 2000 |' under header
    '| speed | speed_progress | speed_cost |' yields
    ('speed_progress','slow')=25 and ('speed_cost','slow')=2000.
    """
    out: dict[tuple[str, str], Any] = {}
    if not os.path.exists(path):
        return out
    header: list[str] | None = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s.startswith("|"):
                header = None  # blank/other line ends the current table
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):  # separator row
                continue
            if header is None:
                header = [c.lower() for c in cells]
                continue
            key = cells[0].lower()
            for i in range(1, len(cells)):
                if cells[i] != "":
                    out[(header[i], key)] = _coerce(cells[i])
    return out


class FinanceGate(CodedTool):
    """Approve or reject a list of proposed MAPs actions based on budget rules."""

    ALWAYS_APPROVE_ACTIONS: ClassVar[frozenset[str]] = frozenset({"wait", "remove"})

    # Fraction of a ride's build cost refunded on `remove` (simulator
    # asset_value = 0.66 x build cost). Used to size the cash available for an
    # upgrade's replacement `place`.
    ASSET_RECOVERY: ClassVar[float] = 0.66

    # Minimum productive days that must remain AFTER a research unlock
    # completes, for the newly-unlocked tier to pay back its build cost.
    # Replaces the old flat 30-day floor, which made mid-game unlocks
    # impossible: the yellow-only cash ramp cleared the affordability bar
    # only around step 64, by which point days_remaining had already
    # dropped below 30, so research never fired in any episode. Payback
    # comes from the rides unlocked after research, not from research IP
    # (which is net-negative per day), so the runway only needs to cover
    # the unlock duration plus this short payback window.
    POST_UNLOCK_MIN_DAYS: ClassVar[int] = 10

    # Upfront cash buffer (in days of research_daily_cost) required to START a
    # research run. The park earns operating profit every day research runs, so
    # it self-funds the tail of a multi-day run -- demanding the FULL run cost
    # upfront (the old behaviour) made research perpetually "almost affordable":
    # blue@slow costs 4d x $2000 = $8000, which the yellow-only ramp only
    # reaches past the episode midpoint, leaving no runway to exploit the
    # unlock. Requiring only the first few days lets research start earlier.
    # NOTE: the coordinator consultation gate (playbook_coordinator) must stay
    # >= this requirement so consultation and approval clear together.
    RESEARCH_UPFRONT_DAYS: ClassVar[int] = 3

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
        placed_shops = args.get("placed_shops") or []
        placed_rides = args.get("placed_rides") or []
        raw_proposals = args.get("proposals") or []
        if isinstance(raw_proposals, str):
            try:
                raw_proposals = json.loads(raw_proposals)
            except json.JSONDecodeError:
                raw_proposals = []
        proposals = raw_proposals if isinstance(raw_proposals, list) else []

        days_remaining = max(0, horizon - step)

        # One-shot lookups shared across all proposals this turn.
        ride_econ = _read_lookup_lines(_RIDES_ECONOMICS_PATH, "rides")
        shop_econ = _read_lookup_lines(_SHOPS_ECONOMICS_PATH, "shops")
        staff_econ = _read_lookup_lines(_STAFF_ECONOMICS_PATH, "staff")
        research_econ = _read_research_lines(_RESEARCH_ECONOMICS_PATH)
        has_food_or_atm = self._scan_food_or_atm(placed_shops)
        has_profitable_ride = self._scan_profitable_ride(placed_rides)

        results: list[dict[str, Any]] = []

        for proposal in proposals:
            enriched = self._enrich(
                proposal,
                ride_econ=ride_econ,
                shop_econ=shop_econ,
                staff_econ=staff_econ,
                research_econ=research_econ,
                has_food_or_atm=has_food_or_atm,
                has_profitable_ride=has_profitable_ride,
            )
            approved, reason = self._evaluate(
                cash=cash,
                days_remaining=days_remaining,
                recurring_daily=recurring_daily,
                action=enriched["action"],
                entity_type=enriched["type"],
                subtype=enriched["subtype"],
                subclass=enriched["subclass"],
                one_time_cost=enriched["one_time_cost"],
                is_research=enriched["is_research"],
                research_daily_cost=enriched["research_daily_cost"],
                research_days=enriched["research_days"],
                has_food_or_atm=enriched["has_food_or_atm"],
                has_profitable_ride=enriched["has_profitable_ride"],
                upgrade_to_subclass=enriched["upgrade_to_subclass"],
                upgrade_to_cost=enriched["upgrade_to_cost"],
                current_tier_refund=enriched["current_tier_refund"],
            )
            row: dict[str, Any] = {
                "label":    enriched["label"],
                "approved": approved,
                "reason":   reason,
            }
            # Only ship the full enriched proposal when the coordinator
            # might actually dispatch it. Rejected rows save ~300 chars
            # each; the coordinator still has the original specialist
            # reply to read if needed.
            if approved:
                row["proposal"] = enriched
            results.append(row)

        return {
            "results":         results,
            "cash":            cash,
            "recurring_daily": recurring_daily,
            "days_remaining":  days_remaining,
        }

    def _enrich(
        self,
        proposal: dict[str, Any],
        *,
        ride_econ: dict, shop_econ: dict, staff_econ: dict, research_econ: dict,
        has_food_or_atm: bool, has_profitable_ride: bool,
    ) -> dict[str, Any]:
        """Fill in derived fields the LLM used to compute itself."""
        action = str(proposal.get("action", "")).lower().strip()
        entity_type = str(proposal.get("type", "")).lower().strip()
        subtype = str(proposal.get("subtype", "")).lower().strip()
        subclass = str(proposal.get("subclass", "")).lower().strip()
        research_speed = str(proposal.get("research_speed", "none")).lower().strip()

        # one_time_cost — building_cost for place, salary for staff, 0 otherwise.
        one_time_cost = 0
        if action == "place" and entity_type in ("ride", "shop"):
            tier = (entity_type + "s", subtype, subclass)
            one_time_cost = self._int((
                ride_econ if entity_type == "ride" else shop_econ
            ).get(tier, {}).get("building_cost", 0))
        elif action == "place" and entity_type == "staff":
            one_time_cost = self._int(staff_econ.get(("staff", subtype, subclass), {}).get("salary", 0))

        # Upgrade-intent remove: a `remove` of a ride that the rides_manager
        # wants to replace with a higher tier on the same plot. The replacement
        # tier rides on `upgrade_to_subclass`; we precompute the replacement's
        # build cost and the refund this remove returns so _evaluate can gate
        # the remove on the replacement actually being affordable + in time.
        upgrade_to_subclass = str(proposal.get("upgrade_to_subclass", "")).lower().strip()
        upgrade_to_cost = 0
        current_tier_refund = 0
        if action == "remove" and entity_type == "ride" and upgrade_to_subclass:
            upgrade_to_cost = self._int(
                ride_econ.get(("rides", subtype, upgrade_to_subclass), {}).get("building_cost", 0)
            )
            current_build_cost = self._int(
                ride_econ.get(("rides", subtype, subclass), {}).get("building_cost", 0)
            )
            current_tier_refund = int(current_build_cost * self.ASSET_RECOVERY)

        # is_research only for set_research with a non-none speed.
        is_research = (action == "set_research" and research_speed != "none")

        # Research costs.
        research_daily_cost = self._int(research_econ.get(("speed_cost", research_speed), 0))
        if is_research:
            target_tier = str(proposal.get("target_tier") or "blue").lower()
            points_required = self._int(research_econ.get(("points_required", target_tier), 0))
            speed_progress = self._int(research_econ.get(("speed_progress", research_speed), 0))
            research_days = math.ceil(points_required / speed_progress) if speed_progress > 0 else 0
        else:
            research_days = 0

        # Label — short human-readable.
        if action == "set_research":
            label = f"set_research speed={research_speed} topics={proposal.get('research_topics') or '[]'}"
        elif action == "wait":
            label = "wait"
        elif entity_type and subtype and subclass:
            label = f"{action} {subclass} {subtype}".strip()
        else:
            label = action or "unknown"

        return {
            "label":               label,
            "action":              action,
            "type":                entity_type,
            "subtype":             subtype,
            "subclass":            subclass,
            "price":               self._int(proposal.get("price", 0)),
            "order_quantity":      self._int(proposal.get("order_quantity", 0)),
            "x":                   proposal.get("x"),
            "y":                   proposal.get("y"),
            "research_speed":      research_speed if action == "set_research" else None,
            "research_topics":     proposal.get("research_topics") if action == "set_research" else None,
            "one_time_cost":       one_time_cost,
            "is_research":         is_research,
            "research_daily_cost": research_daily_cost,
            "research_days":       research_days,
            "has_food_or_atm":     has_food_or_atm,
            "has_profitable_ride": has_profitable_ride,
            "upgrade_to_subclass": upgrade_to_subclass or None,
            "upgrade_to_cost":     upgrade_to_cost,
            "current_tier_refund": current_tier_refund,
        }

    @staticmethod
    def _scan_food_or_atm(placed_shops: Any) -> bool:
        if not isinstance(placed_shops, list):
            return False
        for shop in placed_shops:
            if not isinstance(shop, dict):
                continue
            subtype = str(shop.get("subtype", "")).lower()
            subclass = str(shop.get("subclass", "")).lower()
            if subtype == "food":
                return True
            if subtype == "specialty" and subclass == "green":
                return True
        return False

    @staticmethod
    def _scan_profitable_ride(placed_rides: Any) -> bool:
        if not isinstance(placed_rides, list):
            return False
        for ride in placed_rides:
            if not isinstance(ride, dict):
                continue
            if not ride.get("out_of_service", False):
                return True
        return False

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
        upgrade_to_subclass: str | None = None,
        upgrade_to_cost: int = 0,
        current_tier_refund: int = 0,
    ) -> tuple[bool, str]:
        # Rule 1 — wait: free, always go ahead
        if action == "wait":
            return True, "always approved"

        # Rule 2 — remove: recovers 66% of build cost, always beneficial
        if action == "remove":
            # Plain remove (no upgrade intent): always beneficial.
            if not upgrade_to_subclass:
                return True, "always approved: sell recovers 66% of build cost"
            # Upgrade-intent remove: only tear out the yellow if the replacement
            # ride would itself clear break-even AND fit cash after the refund.
            # Otherwise we'd strand an empty plot for the rest of the episode.
            be_days = self.BREAK_EVEN_DAYS.get(subtype, {}).get(upgrade_to_subclass)
            if be_days is not None and days_remaining < be_days:
                return False, (
                    f"upgrade to {subtype}/{upgrade_to_subclass} needs ~{be_days} "
                    f"days to break even but only {days_remaining} steps remain; "
                    "keep the existing ride rather than strand the plot"
                )
            cash_after_swap = cash + current_tier_refund - upgrade_to_cost
            if cash_after_swap < recurring_daily:
                return False, (
                    f"upgrade to {subtype}/{upgrade_to_subclass}: cash after "
                    f"refund (+${current_tier_refund}) and rebuild "
                    f"(-${upgrade_to_cost}) is ${cash_after_swap} < 1-day "
                    f"recurring ${recurring_daily}; defer the swap"
                )
            return True, (
                f"upgrade remove approved: replacement {subtype}/"
                f"{upgrade_to_subclass} fits runway ({days_remaining} steps) "
                f"and budget (cash after swap ${cash_after_swap})"
            )

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
            min_runway = research_days + self.POST_UNLOCK_MIN_DAYS
            if days_remaining < min_runway:
                return False, (
                    f"only {days_remaining} steps remain; need {min_runway} "
                    f"(unlock {research_days}d + {self.POST_UNLOCK_MIN_DAYS}d "
                    "payback window for the unlocked tier)"
                )
            upfront_days = min(research_days, self.RESEARCH_UPFRONT_DAYS)
            total_needed = research_daily_cost * upfront_days + recurring_daily
            if cash < total_needed:
                return False, (
                    f"need ${total_needed} ({upfront_days}d research upfront + "
                    f"1-day buffer; remaining days self-funded by operating "
                    f"profit), have ${cash}"
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
