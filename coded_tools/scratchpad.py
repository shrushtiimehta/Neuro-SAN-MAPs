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
One-run scratchpad, one pad per agent network.

Each network is invoked as a series of short, near-historyless runs — player
once per step, watcher every 10 steps, planner at episode start/end — so a plan
that spans two runs ("removed the yellow drink shop, place the blue one next
run") has nowhere to live. This is that place: a few lines a network writes at
the end of a run and consumes at the start of its next one.

The pad is keyed by the `pad` arg, bound per network in the HOCON (never passed
by the LLM), so player/watcher/planner cannot read or clobber each other's note.

READ-AND-CLEAR: reading returns the note and deletes it, so a note is visible
for exactly ONE run and never silently rots into stale advice. Writing replaces
whatever is there — there is no append, and no history.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

_DIR = Path("coded_tools/state")


def _path(pad: Any) -> Path:
    """Pad file for one network. Sanitized because `pad` reaches a filesystem path."""
    name = re.sub(r"[^a-z0-9_]", "", str(pad or "").lower()) or "player"
    return _DIR / f"scratchpad_{name}.md"


class Scratchpad(CodedTool):
    """Write a note for this network's next run, or read-and-clear the one it left last run."""

    MAX_LINES: ClassVar[int] = 5
    MAX_CHARS: ClassVar[int] = 600

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: dict with an optional ``note`` key and a ``pad`` key bound by config.
            - ``note`` present and non-empty: replace this network's pad with it,
              trimmed to MAX_LINES lines / MAX_CHARS characters.
            - ``note`` absent: return this network's current note and DELETE it.
            - ``pad``: network key from the HOCON (player|watcher|planner).
        :param sly_data: ignored.
        :return: {"status", "action", "pad", "note"} or an "ERROR: ..." string.
        """
        del sly_data
        note = (args.get("note") or "").strip()
        path = _path(args.get("pad"))
        try:
            if note:
                trimmed = "\n".join(note.splitlines()[: self.MAX_LINES])[: self.MAX_CHARS]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(trimmed, encoding="utf-8")
                return {"status": "ok", "action": "wrote", "pad": path.stem, "note": trimmed}

            previous = path.read_text(encoding="utf-8").strip() if path.exists() else ""
            path.unlink(missing_ok=True)
            return {"status": "ok", "action": "read_and_cleared", "pad": path.stem, "note": previous}
        except OSError as err:
            self.logger.warning("scratchpad %s failed: %s", "write" if note else "read", err)
            return f"ERROR: scratchpad unavailable: {err}"

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)
