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
Shared parsers for the trial files, used by ActiveTrials and ResolveTrials.

trial_strategies.md line:  "- <trial_id>: <rule body>"
trial_strategies_criteria.md line:
  "- <trial_id> ep=<N> step_start=<S> domain=<D> section='<X>'
     edit=<add_line|replace_line> [find='<F>'] rationale='<R>'
     success='<SC>' failure='<FC>'"
"""

from __future__ import annotations

import re
from typing import Any

from coded_tools.file_io import FileIO

STRATEGIES_PATH = "coded_tools/state/trial_strategies.md"
CRITERIA_PATH = "coded_tools/state/trial_strategies_criteria.md"
OUTCOME_PATH = "coded_tools/state/trial_strategies_outcome.md"

_STRATEGY_RE = re.compile(r"^-\s+(\S+):\s+(.*)$")
# key=value pairs where the value is either a single-quoted string (may contain
# spaces) or a bare token.
_KV_RE = re.compile(r"(\w+)=('[^']*'|\S+)")


def read_text(path: str) -> str:
    """Backwards-compatible alias for :meth:`FileIO.read_text`."""
    return FileIO.read_text(path)


def parse_strategies(text: str) -> dict[str, str]:
    """{trial_id: rule_body} from trial_strategies.md text."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        match = _STRATEGY_RE.match(line.strip())
        if match:
            out[match.group(1)] = match.group(2).strip()
    return out


def parse_criteria(text: str) -> dict[str, dict[str, Any]]:
    """{trial_id: {ep, step_start, domain, section, edit, find, rationale,
    success, failure}} from trial_strategies_criteria.md text."""
    out: dict[str, dict[str, Any]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        parts = line[2:].split(None, 1)
        if not parts:
            continue
        trial_id = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        fields: dict[str, Any] = {}
        for key, value in _KV_RE.findall(rest):
            if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
                value = value[1:-1]
            fields[key] = value
        out[trial_id] = fields
    return out
