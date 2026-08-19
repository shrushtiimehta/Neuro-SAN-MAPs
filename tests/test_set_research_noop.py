"""A `set_research` must actually change something, or it is a wasted turn.

Two real failures from episode 0, step 14, where a proposal meaning "research
toward blue" fired as "keep research off" and burned one of the run's 100 turns:

  1. FinanceGate defaulted a MISSING research_speed to "none", inverting the
     intent, and — because that reads as "not research" — priced it as free.
  2. ProposeAction accepted speed="none" while the park was ALREADY at "none".
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coded_tools.finance_gate import FinanceGate  # noqa: E402
from coded_tools.propose_action import ProposeAction  # noqa: E402


def _obs(speed, topics=None):
    # Shape ProposeAction actually receives: _read_latest_obs returns the INNER
    # observation, not the cache entry. The old {"observation": {...}} fixture
    # matched the guard's bug, so the no-op test passed while ep3/step17 shipped one.
    return {"research_speed": speed, "research_topics": topics or ["carousel"],
            "money": 5000, "step": 14}


def test_missing_speed_is_rejected_not_defaulted():
    ok, why = ProposeAction()._check_set_research_fields(
        {"research_topics": ["carousel"]}, _obs("none"))
    assert not ok and "explicit research_speed" in why


def test_setting_the_speed_already_running_is_rejected():
    check = ProposeAction()._check_set_research_fields
    assert not check({"research_speed": "none"}, _obs("none"))[0]      # the step-14 bug
    assert "changes nothing" in check({"research_speed": "none"}, _obs("none"))[1]
    assert not check({"research_speed": "slow"}, _obs("slow"))[0]      # same, any speed

    # Same speed but a DIFFERENT topic set re-aims research — a real move.
    assert check({"research_speed": "slow", "research_topics": ["food"]},
                 _obs("slow", ["carousel"]))[0]

    # Turning ACTIVE research off is a real decision — it stops a daily fee.
    assert check({"research_speed": "none"}, _obs("fast"))[0]
    # And starting it is obviously fine.
    assert check({"research_speed": "fast"}, _obs("none"))[0]
    # No observation to compare against -> allow; never block on missing state.
    assert check({"research_speed": "slow"}, None)[0]


def test_bad_speed_still_rejected():
    ok, why = ProposeAction()._check_set_research_fields({"research_speed": "turbo"}, _obs("none"))
    assert not ok and "must be one of" in why


def test_financegate_does_not_invent_a_speed():
    """A set_research with no speed must not come back enriched as speed='none'.

    That default is what made the bug invisible: it also flipped is_research to
    False, so the gate priced the turn as free instead of questioning it.
    """
    enriched = FinanceGate()._enrich(
        {"action": "set_research", "research_topics": ["carousel"]},
        ride_econ={}, shop_econ={}, staff_econ={}, research_econ={},
        has_food_or_atm=True, has_profitable_ride=True,
    )
    assert enriched.get("research_speed") != "none", "missing speed defaulted to 'none' again"

    # A real speed still enriches normally.
    live = FinanceGate()._enrich(
        {"action": "set_research", "research_speed": "fast", "research_topics": ["carousel"]},
        ride_econ={}, shop_econ={}, staff_econ={}, research_econ={},
        has_food_or_atm=True, has_profitable_ride=True,
    )
    assert live.get("research_speed") == "fast"


if __name__ == "__main__":
    test_missing_speed_is_rejected_not_defaulted()
    test_setting_the_speed_already_running_is_rejected()
    test_bad_speed_still_rejected()
    test_financegate_does_not_invent_a_speed()
    print("ok")
