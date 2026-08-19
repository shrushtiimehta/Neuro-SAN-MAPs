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
"""MAPS_INCLUDE_ARCHIVED: does 'best-ever' span prior runs, or stop at this one?"""

import json
import os
import tempfile

from coded_tools.run_telemetry import RunTelemetry


def _write_episode(run_dir: str, ep: int, final_cum: float) -> None:
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, f"run.ep{ep:03d}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for step, cum in ((1, 0.0), (2, final_cum)):
            fh.write(json.dumps({"episode": ep, "step": step, "cumulative_reward": cum}) + "\n")


def test_include_archived_flag() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # Current run: ep0 (weak) + ep1 (the most recent). Archived run: the best score ever.
        _write_episode(tmp, 0, 100.0)
        _write_episode(tmp, 1, 50.0)
        _write_episode(os.path.join(tmp, RunTelemetry.PRIOR_RUNS_SUBDIR, "20260101-000000"), 3, 900.0)

        telemetry = RunTelemetry()
        telemetry.RUN_LOG_DIR = tmp

        os.environ.pop(RunTelemetry.ENV_INCLUDE_ARCHIVED, None)
        with_archived = telemetry.invoke({"select": "best"}, {})
        assert with_archived["include_archived"] is True
        assert with_archived["reference_episode"]["final_cum"] == 900.0
        assert telemetry.invoke({"num_runs": 5}, {})["runs_analyzed"] == 2

        # run_all.sh --no-archived exports the switch: current run only.
        os.environ[RunTelemetry.ENV_INCLUDE_ARCHIVED] = "0"
        try:
            current_only = telemetry.invoke({"select": "best"}, {})
            assert current_only["include_archived"] is False
            assert current_only["reference_episode"]["run_id"] == "current"
            assert current_only["reference_episode"]["final_cum"] == 100.0
            assert telemetry.invoke({"num_runs": 5}, {})["runs_analyzed"] == 1
        finally:
            del os.environ[RunTelemetry.ENV_INCLUDE_ARCHIVED]


if __name__ == "__main__":
    test_include_archived_flag()
    print("ok")
