# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# END COPYRIGHT
"""Self-check for the runner's early-abort guardrail (verdict parse + strike
machine). Run: `pytest tests/apps/maps_park/test_abort_verdict.py` (asserts, no deps)."""

from apps.maps_park.runner import (
    ABORT_EARLIEST_STEP,
    ABORT_HALFWAY_STEP,
    ABORT_MIN_STRIKES,
    _doom_decision,
    _parse_verdict,
)


def test_parse_verdict():
    assert _parse_verdict("VERDICT: doomed | cum flat, park_value 40% below best@40") == "doomed"
    assert _parse_verdict("VERDICT: on_track | tracking best") == "on_track"
    assert _parse_verdict("VERDICT: on track") == "on_track"          # space variant
    assert _parse_verdict("verdict: UNDERPERFORMING | slow") == "underperforming"
    assert _parse_verdict("some preamble\nVERDICT: doomed\nmore") == "doomed"
    # A missing/garbage verdict must be None so the runner never aborts on it.
    assert _parse_verdict("no verdict here") is None
    assert _parse_verdict("") is None
    assert _parse_verdict(None) is None


def test_doom_decision():
    mid = ABORT_EARLIEST_STEP + 10                   # past earliest, still before halfway
    assert mid < ABORT_HALFWAY_STEP

    # BEFORE halfway: two consecutive doomed verdicts (10-step grace) -> abort.
    s, ab = _doom_decision(0, "doomed", ABORT_EARLIEST_STEP)
    assert (s, ab) == (1, False)                     # first strike = grace
    s, ab = _doom_decision(s, "doomed", mid)
    assert s == ABORT_MIN_STRIKES and ab is True     # second strike -> abort

    # AT/AFTER halfway: a single doomed verdict aborts immediately.
    s, ab = _doom_decision(0, "doomed", ABORT_HALFWAY_STEP)
    assert (s, ab) == (1, True)                      # halfway boundary: no grace
    s, ab = _doom_decision(0, "doomed", ABORT_HALFWAY_STEP + 10)
    assert (s, ab) == (1, True)                      # well past halfway: immediate

    # A recovery in between resets the count (no abort).
    s, ab = _doom_decision(1, "on_track", mid)
    assert (s, ab) == (0, False)
    s, ab = _doom_decision(1, "underperforming", mid)
    assert (s, ab) == (0, False)

    # Never abort before there's enough signal, and never on a parse miss.
    s, ab = _doom_decision(1, "doomed", ABORT_EARLIEST_STEP - 1)
    assert (s, ab) == (1, False)                     # too early: no-op, count held
    s, ab = _doom_decision(1, None, ABORT_HALFWAY_STEP + 10)
    assert (s, ab) == (1, False)                     # unparseable: no-op even past halfway


if __name__ == "__main__":
    test_parse_verdict()
    test_doom_decision()
    print("ok: abort verdict parse + strike machine")
