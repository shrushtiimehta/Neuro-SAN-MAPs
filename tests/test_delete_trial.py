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
"""Self-check for DeleteTrial: prune a micro trial, refuse a macro one.

Seeds a throwaway pair of trial files (real state untouched) with one macro and
one micro trial, then verifies: deleting the micro removes it from both files
and appends a 'falsified' outcome; deleting the macro or an unknown id is
refused; and the macro trial survives untouched.
Run: `python tests/test_delete_trial.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import os
import tempfile

from coded_tools import delete_trial
from coded_tools.delete_trial import DeleteTrial

MACRO_STRAT = "- t3_1: rides.add_line coaster\n"
MICRO_STRAT = "- t3_2: shops.add_line kiosk\n"
MACRO_CRIT = "- t3_1 ep=3 step_start=1 domain=rides origin=macro section='rides' edit=add_line rationale='r' success='s' failure='f'\n"
MICRO_CRIT = "- t3_2 ep=3 step_start=40 domain=shops origin=micro section='shops' edit=add_line rationale='r' success='s' failure='f'\n"


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_delete_trial() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        strat = os.path.join(tmp, "trial_strategies.md")
        crit = os.path.join(tmp, "trial_strategies_criteria.md")
        outcome = os.path.join(tmp, "trial_strategies_outcome.md")
        delete_trial.STRATEGIES_PATH = strat
        delete_trial.CRITERIA_PATH = crit
        delete_trial.OUTCOME_PATH = outcome

        _write(strat, MACRO_STRAT + MICRO_STRAT)
        _write(crit, MACRO_CRIT + MICRO_CRIT)

        tool = DeleteTrial()

        # 1. Delete the micro trial -> success; gone from both files.
        result = tool.invoke({"trial_id": "t3_2"}, {})
        assert result == {"deleted": "t3_2", "outcome": "falsified"}, result
        assert "t3_2" not in _read(strat), "micro strategy line not removed"
        assert "t3_2" not in _read(crit), "micro criteria line not removed"

        # 2. Outcome ledger got a falsified line so the planner won't re-propose it.
        out_text = _read(outcome)
        assert "trial_id=t3_2" in out_text and "outcome=falsified" in out_text, out_text

        # 3. The macro trial is untouched...
        assert "t3_1" in _read(strat) and "t3_1" in _read(crit), "macro trial wrongly dropped"

        # 4. ...and refuses to be deleted mid-episode.
        macro_result = tool.invoke({"trial_id": "t3_1"}, {})
        assert isinstance(macro_result, str) and macro_result.startswith("ERROR:"), macro_result
        assert "t3_1" in _read(strat), "refused macro delete must leave the file intact"

        # 5. Unknown / already-removed id is an error, not a silent no-op.
        assert str(tool.invoke({"trial_id": "t3_2"}, {})).startswith("ERROR:")
        assert str(tool.invoke({"trial_id": ""}, {})).startswith("ERROR:")

    print("delete-trial OK: micro pruned + falsified-logged, macro/unknown refused")


if __name__ == "__main__":
    test_delete_trial()
