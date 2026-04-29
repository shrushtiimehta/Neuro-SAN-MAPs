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
Per-park rolling observation window.

Keeps the last N post-step observation envelopes for each of the 5 parks in
a small JSON file, separate from the larger persistent_memory blob. Default
window is 2 — that's enough for the agent to reason about deltas (cash
before/after, reward delta, broken-ride drift) without paying the cost of
shipping the whole episode history.

File path:  ./memory/maps_park/latest_observations.json
            (override with MAPS_LATEST_OBS_PATH env var)
Window:     last 2 observations per park (override with
            MAPS_OBS_WINDOW env var)
File shape: {"park_0": [obs_n_minus_1, obs_n], "park_1": [...], ...}

park_director reads its park's window at turn start, passes the trailing
observation (and optionally the prior one for delta reasoning) to
strategy_coordinator, then writes the newly returned envelope back here
after each ActionDispatcher call.
"""

from __future__ import annotations

import json
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


class LatestObservation(CodedTool):
    """Read or append-write the rolling observation window for one park."""

    DEFAULT_PATH: ClassVar[str] = os.environ.get(
        "MAPS_LATEST_OBS_PATH",
        "./memory/maps_park/latest_observations.json",
    )
    DEFAULT_WINDOW: ClassVar[int] = int(os.environ.get("MAPS_OBS_WINDOW", "2"))

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        mode = args.get("mode")
        if mode not in {"read", "write"}:
            return {"error": f"mode must be 'read' or 'write', got {mode!r}"}

        park = args.get("park")
        if park is None:
            return {"error": "park is required (slot 0..4)"}
        try:
            park_idx = int(park)
        except (TypeError, ValueError):
            return {"error": f"park must be int-coercible, got {park!r}"}
        park_key = f"park_{park_idx}"

        if mode == "read":
            return self._read(park_key)

        observation = args.get("observation")
        if not isinstance(observation, dict):
            return {
                "error": (
                    f"observation must be an object/dict for mode=write, "
                    f"got {type(observation).__name__}"
                )
            }
        return self._write(park_key, observation)

    def _read(self, park_key: str) -> dict[str, Any]:
        data = self._load_file()
        if isinstance(data, dict) and "error" in data:
            return data
        window = self._get_window(data, park_key)
        return {
            "park_key": park_key,
            "window_size": len(window),
            "previous": window[-2] if len(window) >= 2 else None,
            "latest": window[-1] if window else None,
        }

    def _write(self, park_key: str, observation: dict[str, Any]) -> dict[str, Any]:
        data = self._load_file()
        if isinstance(data, dict) and "error" in data:
            # Best-effort: if the file was corrupt, overwrite cleanly.
            data = {}
        elif data is None:
            data = {}

        window = list(self._get_window(data, park_key))
        window.append(observation)
        max_window = max(1, self.DEFAULT_WINDOW)
        trimmed = window[-max_window:]
        data[park_key] = trimmed

        path = self._path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as err:
            return {"error": f"failed to write {path}: {err}", "park_key": park_key}

        return {
            "park_key": park_key,
            "written": True,
            "window_size": len(trimmed),
        }

    def _load_file(self) -> dict[str, Any] | None:
        path = self._path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as fh:
                loaded = json.load(fh)
        except (OSError, json.JSONDecodeError) as err:
            return {"error": f"failed to read {path}: {err}"}
        if not isinstance(loaded, dict):
            return {"error": f"file at {path} is not a JSON object"}
        return loaded

    def _get_window(self, data: dict[str, Any] | None, park_key: str) -> list[Any]:
        if not isinstance(data, dict):
            return []
        existing = data.get(park_key)
        if isinstance(existing, list):
            return existing
        if isinstance(existing, dict):
            # Backwards-compat: a single observation dict was stored
            # under the previous "latest only" schema.
            return [existing]
        return []

    def _path(self) -> str:
        return self.DEFAULT_PATH
