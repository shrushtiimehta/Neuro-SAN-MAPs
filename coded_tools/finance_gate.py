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

  1. action='survey_guests'               → APPROVE only when cash >= $500 × num_guests;
                                            REJECT otherwise (env charges $500/guest,
                                            max 25 guests, and counts the turn as wait)
  2. action='remove'                      → always APPROVE (recovers 66% of build cost;
                                            a tier upgrade is just remove + place)
  3. action='move'                        → always APPROVE (free to relocate)
                                            when cash >= daily_operating_cost
  4. specialty/red (Billboard)            → REJECT unless has_food_or_atm=True
                                            (Billboard earns $0 directly)
  5. action='place', type='ride'          → REJECT if days_remaining <
                                            BREAK_EVEN_DAYS[subtype][subclass]
                                            (computed from economics files at
                                            5 ops/day assumption)
  6. action='set_research', speed='none'  → APPROVE immediately (stopping
                                            research costs nothing)
     action='set_research', speed!=none   → APPROVE only when ALL of:
       (a) has_profitable_ride=True
       (b) days_remaining >= research_days + POST_UNLOCK_MIN_DAYS
       (c) cash >= research_daily_cost * research_days + daily_operating_cost
  7. Everything else                      → APPROVE when:
       cash - one_time_cost >= daily_operating_cost (keep 1-day buffer)

daily_operating_cost is the park's REAL daily burn — staff salaries + research
speed cost + the sim's realized per-day operating_cost of every placed ride and
shop. See FinanceGate.operating_cost for why the last two are read back from the
observation rather than estimated from the economics tables.

Break-even days come from the `break_even_days` column of
config_files/economics_rides.md — the single source of truth. They were derived
at 5 ops/day (moderate-park assumption):
  break_even_ops  = ceil(building_cost / (max_ticket_price * capacity - operating_cost))
  break_even_days = ceil(break_even_ops / 5)
"""

from __future__ import annotations

import json
import math
import os
import re
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

# The observation names a ride's price `ticket_price` and a shop's `item_price`,
# but the env action takes plain `price` for both. Specialists read one name and
# write the other, so both tools that touch a proposal fold the alias in first.
_PRICE_ALIASES = ("ticket_price", "item_price")


def normalize_price_key(args: Any) -> None:
    """Fold a `ticket_price`/`item_price` alias into `price`. Mutates in place."""
    if not isinstance(args, dict):
        return
    for alias in _PRICE_ALIASES:
        value = args.pop(alias, None)
        if value is not None and args.get("price") is None:
            args["price"] = value


_SURVEY_GUESTS_COST_PER_GUEST = 500
_SURVEY_GUESTS_MAX = 25

# ParkStatus (called by the runner each turn) writes this lean slice; FinanceGate
# reads cash/step/placed_*/research_speed straight from it so the coordinator only
# has to pass `proposals` — no per-field copy-paste on the LLM hop. Explicit args
# still override (tests / direct callers).
_STATUS_COORDINATOR_PATH = "coded_tools/state/status_coordinator.json"


def _load_status_slice() -> dict[str, Any]:
    try:
        with open(_STATUS_COORDINATOR_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

_RIDES_ECONOMICS_PATH = "coded_tools/config_files/economics_rides.md"
_SHOPS_ECONOMICS_PATH = "coded_tools/config_files/economics_shops.md"
_STAFF_ECONOMICS_PATH = "coded_tools/config_files/economics_staff.md"
_RESEARCH_ECONOMICS_PATH = "coded_tools/config_files/economics_research.md"


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

    # Break-even days are NOT duplicated here: _enrich reads the break_even_days
    # column out of economics_rides.md, the same file the costs come from, so the
    # table and the gate can never drift apart.

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        # Everything except `proposals` comes straight from the status slice the
        # runner refreshes each turn — the agent passes only proposals.
        status = _load_status_slice()
        cash = self._int(status.get("cash", 0))
        step = self._int(status.get("step", 0))
        horizon = 100  # episode length (medium difficulty)
        placed_shops = status.get("placed_shops") or []
        placed_rides = status.get("placed_rides") or []
        placed_staff = status.get("placed_staff") or []
        research_speed = str(status.get("research_speed") or "none").lower().strip()
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

        # DailyOperatingCost is MERGED into FinanceGate: the per-day operating
        # cost (staff salaries + research speed cost) is derived here from the
        # placed staff and research speed, so callers no longer compute it in a
        # separate tool. An explicit daily_operating_cost arg still overrides
        # (back-compat / direct callers).
        if args.get("daily_operating_cost") is not None:
            daily_operating_cost = self._int(args.get("daily_operating_cost"))
        else:
            daily_operating_cost = self.operating_cost(
                placed_staff, research_speed, staff_econ, research_econ,
                placed_rides, placed_shops,
            )

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
                available_entities=status.get("available_entities"),
            )
            approved, reason = self._evaluate(
                cash=cash,
                days_remaining=days_remaining,
                daily_operating_cost=daily_operating_cost,
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
                num_guests=enriched["num_guests"],
                break_even_days=enriched["break_even_days"],
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
            "daily_operating_cost": daily_operating_cost,
            "days_remaining":  days_remaining,
        }

    @staticmethod
    def operating_cost(
        placed_staff: Any, research_speed: str, staff_econ: dict, research_econ: dict,
        placed_rides: Any = None, placed_shops: Any = None,
    ) -> int:
        """The park's real per-day burn: staff salaries + research speed cost +
        the realized daily operating_cost of every placed ride and shop.

        Salaries and the speed cost are contractual, so they come from the
        economics tables. Ride and shop costs are NOT: a ride is charged
        cost_per_operation per operation and a shop is charged
        order_quantity x item_cost at stock time, both of which depend on how the
        day actually ran. So we take the sim's own realized `operating_cost` off
        each placed entity rather than estimating ops/day.

        ponytail: yesterday's realized figure, one day stale by construction —
        a ride placed or a shop re-ordered this turn reads 0 until it has run a
        day. Fixing that properly needs a forward cost estimate from the sim.
        Previously this counted ONLY salaries + research, which understated the
        burn by the two largest costs in a mature park (~$10k/day of ride ops
        alone in the best run), making the "1-day buffer" rule vacuous.
        """
        total = 0
        for entry in placed_staff or []:
            if not isinstance(entry, dict):
                continue
            subtype = str(entry.get("subtype", "")).lower().strip()
            subclass = str(entry.get("subclass", "")).lower().strip()
            salary = staff_econ.get(("staff", subtype, subclass), {}).get("salary", 0)
            total += FinanceGate._int(salary)
        speed = str(research_speed or "none").lower().strip()
        total += FinanceGate._int(research_econ.get(("speed_cost", speed), 0))
        for placed in (placed_rides, placed_shops):
            for entry in placed or []:
                if isinstance(entry, dict):
                    total += FinanceGate._int(entry.get("operating_cost", 0))
        return total

    def _enrich(
        self,
        proposal: dict[str, Any],
        *,
        ride_econ: dict, shop_econ: dict, staff_econ: dict, research_econ: dict,
        has_food_or_atm: bool, has_profitable_ride: bool,
        available_entities: dict | None = None,
    ) -> dict[str, Any]:
        """Fill in derived fields the LLM used to compute itself."""
        action = str(proposal.get("action", "")).lower().strip()
        entity_type = str(proposal.get("type", "")).lower().strip()
        subtype = str(proposal.get("subtype", "")).lower().strip()
        subclass = str(proposal.get("subclass", "")).lower().strip()
        # Do NOT default a missing speed to "none": on a set_research proposal that
        # silently inverts the intent ("research toward blue" -> "keep research off"),
        # and because is_research below then reads False, the gate prices it as free
        # and waves the no-op through. Missing stays missing so ProposeAction can
        # reject it. For every other action the field is nulled out at the end anyway.
        research_speed = str(proposal.get("research_speed") or "").lower().strip()

        # one_time_cost — building_cost for place, salary for staff, 0 otherwise.
        one_time_cost = 0
        if action == "place" and entity_type in ("ride", "shop"):
            tier = (entity_type + "s", subtype, subclass)
            one_time_cost = self._int((
                ride_econ if entity_type == "ride" else shop_econ
            ).get(tier, {}).get("building_cost", 0))
        elif action == "place" and entity_type == "staff":
            one_time_cost = self._int(staff_econ.get(("staff", subtype, subclass), {}).get("salary", 0))

        # is_research only for set_research that actually turns research ON.
        # "" (speed omitted) counts as off here too, so a malformed proposal is
        # never priced as if it were researching.
        is_research = (action == "set_research" and research_speed not in ("", "none"))

        # Runway a ride needs to recoup its build cost, read straight off the
        # economics table. 0 for anything that isn't a known ride tier (shops,
        # staff, a subtype the table doesn't carry) — the gate then skips the rule.
        break_even_days = self._int(
            ride_econ.get(("rides", subtype, subclass), {}).get("break_even_days", 0)
        )

        # Research cost is a FLAT per-speed daily fee — the sim charges it once
        # regardless of how many research_topics are selected (topics only pick
        # WHICH subtypes are eligible; the sim researches them in its own fixed
        # order). Confirmed against the MAPs simulator (research.js).
        research_daily_cost = self._int(research_econ.get(("speed_cost", research_speed), 0))
        if is_research:
            next_tier = self._next_tier(available_entities, proposal.get("research_topics"))
            points_required = self._int(research_econ.get(("points_required", next_tier), 0))
            speed_progress = self._int(research_econ.get(("speed_progress", research_speed), 0))
            research_days = math.ceil(points_required / speed_progress) if speed_progress > 0 else 0
        else:
            research_days = 0

        # Label — short human-readable.
        if action == "set_research":
            label = (f"set_research speed={research_speed or '<missing>'} "
                     f"topics={proposal.get('research_topics') or '[]'}")
        elif action == "wait":
            label = "wait"
        elif entity_type and subtype and subclass:
            label = f"{action} {subclass} {subtype}".strip()
        else:
            label = action or "unknown"

        # `price` is intentionally NOT derived here. ProposeAction is the single
        # source of truth for price: it deterministically forces the economics
        # value (max_ticket_price / max_item_price / salary) at the env boundary,
        # AFTER the LLM coordinator has picked an action — so a price set here
        # could only be mangled on that hop anyway. FinanceGate's budget rules
        # never read price (only building_cost / salary), so we pass the raw
        # proposal value through untouched.
        # Fold ticket_price/item_price into price BEFORE the rebuild below, which
        # keeps a fixed key list and would otherwise drop the alias silently.
        normalize_price_key(proposal)
        price = self._int(proposal.get("price", 0))

        return {
            "label":               label,
            "action":              action,
            "type":                entity_type,
            "subtype":             subtype,
            "subclass":            subclass,
            "price":               price,
            "order_quantity":      self._int(proposal.get("order_quantity", 0)),
            "x":                   proposal.get("x"),
            "y":                   proposal.get("y"),
            "research_speed":      research_speed if action == "set_research" else None,
            "research_topics":     proposal.get("research_topics") if action == "set_research" else None,
            "one_time_cost":       one_time_cost,
            "break_even_days":     break_even_days,
            "is_research":         is_research,
            "research_daily_cost": research_daily_cost,
            "research_days":       research_days,
            "has_food_or_atm":     has_food_or_atm,
            "has_profitable_ride": has_profitable_ride,
            "num_guests":          self._int(proposal.get("num_guests", 0)),
        }

    # Tier ladder, cheapest first. Yellow is owned from the start, so a research
    # run is always aimed at the first of these a subtype has not reached yet.
    _TIER_ORDER: ClassVar[tuple[str, ...]] = ("blue", "green", "red")

    @classmethod
    def _next_tier(cls, available_entities: Any, topics: Any) -> str:
        """The tier the next unlock will actually buy, for pricing the run.

        Replaces the LLM-supplied `target_tier`, which defaulted to "blue" and so
        priced a green run at half its points and a red run at a quarter — the gate
        then approved runs the runway could never finish. Research runs breadth
        first, so with several topics listed the FIRST unlock is the lowest tier
        any of them is still missing; that is the one the budget has to cover.
        Falls back to "blue" when the unlock ledger is unavailable.
        """
        if not isinstance(available_entities, dict) or not available_entities:
            return cls._TIER_ORDER[0]
        names = [str(t).lower().strip() for t in topics] if isinstance(topics, list) else []
        wanted = [n for n in names if n in available_entities] or list(available_entities)
        for tier in cls._TIER_ORDER:
            if any(tier not in (available_entities.get(n) or []) for n in wanted):
                return tier
        return cls._TIER_ORDER[-1]  # everything listed is already at red

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
        """True when ANY placed ride is in service.

        Despite the `has_profitable_ride` key it feeds (kept for wire
        compatibility with player.hocon), this is an in-service check, not a
        revenue>cost one — the coordinator's status slice carries no per-ride
        revenue. It gates research on "the park has something earning", which is
        deliberately loose: research is already the latest-firing lever in the
        run (step 31 in the best episode), so tightening this would delay it further.
        """
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
        daily_operating_cost: int,
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
        num_guests: int = 0,
        break_even_days: int = 0,
    ) -> tuple[bool, str]:
        # wait is always approved
        if action == "wait":
            return True, "wait approved"

        # Rule 1 — survey_guests: costs $500 × num_guests (max 25), reject if unaffordable
        if action == "survey_guests":
            n = max(num_guests, 1)
            total_cost = _SURVEY_GUESTS_COST_PER_GUEST * n
            if cash < total_cost:
                return False, (
                    f"survey_guests({n} guests) costs ${total_cost} "
                    f"(${_SURVEY_GUESTS_COST_PER_GUEST}/guest) but cash is ${cash}; "
                    f"reduce num_guests or wait until cash >= ${total_cost}"
                )
            return True, (
                f"survey_guests approved: ${total_cost} ({n} guests × "
                f"${_SURVEY_GUESTS_COST_PER_GUEST}) fits cash ${cash}"
            )

        # Rule 3 — remove: recovers 66% of build cost, always approved (a tier
        # upgrade is just a plain remove + place of the higher tier, no gating).
        if action == "remove":
            return True, "always approved: sell recovers 66% of build cost"

        # Rule 4 — move: free to relocate; just needs cash to cover daily ops
        if action == "move":
            if cash < daily_operating_cost:
                return False, (
                    f"cash ${cash} < 1-day operating cost ${daily_operating_cost}; "
                    "park can't sustain even a free action"
                )
            return True, "move approved (no relocation cost)"

        # Rule 6 — Billboard (specialty/red): earns $0 directly
        if action == "place" and subtype == "specialty" and subclass == "red":
            if not has_food_or_atm:
                return False, (
                    "Billboard (specialty/red) earns $0 direct revenue; "
                    "reject until food/ATM shops are in place to capture demand"
                )

        # Rule 6b — ride break-even: too late in episode to recoup build cost
        if action == "place" and break_even_days and days_remaining < break_even_days:
            return False, (
                f"{subtype}/{subclass} needs ~{break_even_days} days to break even "
                f"but only {days_remaining} steps remain"
            )

        # Rule 7 — research: capital investment, strict approval criteria
        if action == "set_research" and not is_research:
            return True, "set_research(speed=none) approved: stopping research costs nothing"

        if is_research:
            if not has_profitable_ride:
                return False, (
                    "research requires at least one ride IN SERVICE first; "
                    "every placed ride is out of service (or none is placed)"
                )
            min_runway = research_days + self.POST_UNLOCK_MIN_DAYS
            if days_remaining < min_runway:
                return False, (
                    f"only {days_remaining} steps remain; need {min_runway} "
                    f"(unlock {research_days}d + {self.POST_UNLOCK_MIN_DAYS}d "
                    "payback window for the unlocked tier)"
                )
            upfront_days = min(research_days, self.RESEARCH_UPFRONT_DAYS)
            total_needed = research_daily_cost * upfront_days + daily_operating_cost
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

        # Rule 8 — general cash sufficiency: keep at least 1 day of recurring costs
        cash_after = cash - one_time_cost
        if cash_after < daily_operating_cost:
            return False, (
                f"cash after spend ${cash_after} < 1-day recurring ${daily_operating_cost}"
            )
        return True, f"cash after spend ${cash_after} >= 1-day buffer ${daily_operating_cost}"

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return 0
