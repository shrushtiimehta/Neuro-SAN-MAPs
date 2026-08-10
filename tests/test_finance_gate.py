"""FinanceGate: the daily burn it budgets against, and the ride break-even rule.

`operating_cost` previously counted only staff salaries + research speed cost,
leaving out ride cost_per_operation and shop stocking — the two largest recurring
costs in a mature park (~$10k/day of ride ops alone in the best-scoring episode),
which made the "keep a 1-day buffer" approval rule vacuous.

Break-even days used to be a hand-maintained ClassVar duplicating the
`break_even_days` column of rides_economics.md; they now come from that column.
"""

import asyncio
import json
import os
import shutil

from coded_tools import finance_gate as fgmod
from coded_tools.finance_gate import FinanceGate

_STAFF_ECON = fgmod._read_lookup_lines(fgmod._STAFF_ECONOMICS_PATH, "staff")
_RESEARCH_ECON = fgmod._read_research_lines(fgmod._RESEARCH_ECONOMICS_PATH)

_STAFF = [{"subtype": "janitor", "subclass": "yellow"}]                              # salary 25
_RIDES = [{"subtype": "roller_coaster", "subclass": "blue", "operating_cost": 9000}]
_SHOPS = [{"subtype": "drink", "subclass": "yellow", "operating_cost": 1200}]


def test_operating_cost_includes_ride_and_shop_burn():
    cost = FinanceGate.operating_cost

    contractual = cost(_STAFF, "medium", _STAFF_ECON, _RESEARCH_ECON)
    assert contractual == 25 + 8000  # salary + medium research

    assert cost(_STAFF, "medium", _STAFF_ECON, _RESEARCH_ECON, _RIDES, _SHOPS) == (
        25 + 8000 + 9000 + 1200
    )
    # Omitting the entities (direct callers / no observation yet) is unchanged.
    assert cost(_STAFF, "medium", _STAFF_ECON, _RESEARCH_ECON, None, None) == contractual
    # Non-dict rows in the observation must not blow up the sum.
    assert cost([], "none", _STAFF_ECON, _RESEARCH_ECON, ["junk", None], []) == 0


def _gate(proposals, **status):
    """Run the gate against a temporary status_coordinator slice."""
    path = fgmod._STATUS_COORDINATOR_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    backup = path + ".test_bak"
    if os.path.exists(path):
        shutil.copy(path, backup)
    try:
        slice_ = {"cash": 0, "step": 0, "research_speed": "none",
                  "placed_staff": [], "placed_rides": [], "placed_shops": []}
        slice_.update(status)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(slice_, fh)
        return asyncio.run(FinanceGate().async_invoke({"proposals": json.dumps(proposals)}, {}))
    finally:
        if os.path.exists(backup):
            shutil.move(backup, path)
        elif os.path.exists(path):
            os.remove(path)


def test_gate_rejects_a_spend_the_old_rule_waved_through():
    """cash 9000, blue carousel costs 1500 -> 7500 left, under the 10225 real burn."""
    out = _gate([{"action": "place", "type": "ride",
                  "subtype": "carousel", "subclass": "blue"}],
                cash=9000, step=50, placed_staff=_STAFF,
                placed_rides=_RIDES, placed_shops=_SHOPS)

    assert out["daily_operating_cost"] == 25 + 9000 + 1200
    assert out["results"][0]["approved"] is False
    # Under the old salaries-only burn ($25) this cleared easily.
    assert 9000 - 1500 >= 25


def test_break_even_days_come_from_the_economics_table():
    assert not hasattr(FinanceGate, "BREAK_EVEN_DAYS"), "ClassVar is back; it will drift"

    rc_blue = [{"action": "place", "type": "ride",
                "subtype": "roller_coaster", "subclass": "blue"}]
    # rides_economics.md gives roller_coaster/blue break_even_days = 17.
    assert _gate(rc_blue, cash=100000, step=80)["results"][0]["approved"] is True
    row = _gate(rc_blue, cash=100000, step=90)["results"][0]
    assert row["approved"] is False
    assert "~17 days to break even" in row["reason"], row["reason"]

    # Shops carry no break_even_days column, so the rule must not fire on them.
    shop = [{"action": "place", "type": "shop", "subtype": "food", "subclass": "yellow"}]
    assert _gate(shop, cash=100000, step=99)["results"][0]["approved"] is True


if __name__ == "__main__":
    test_operating_cost_includes_ride_and_shop_burn()
    test_gate_rejects_a_spend_the_old_rule_waved_through()
    test_break_even_days_come_from_the_economics_table()
    print("ok")
