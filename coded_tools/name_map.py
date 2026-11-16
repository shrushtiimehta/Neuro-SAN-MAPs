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
Shared ``name_map`` resolution for the name-based state tools.

StateRead validates the logical ``name`` against the operator-supplied
``name_map`` (deny-by-default) and resolves it to a path. That shared
block lives here so name-based state tools cannot drift apart.
"""

from __future__ import annotations

from typing import Any
from typing import Optional

# Model providers can emit an argument outside a JSON-schema enum.  Keep a
# deliberately tiny compatibility table for synonyms observed in real runs.
# An alias is accepted only when its canonical target is present in the
# operator-controlled name_map, so this never expands filesystem access.
SAFE_READ_ALIASES = {
    "economics": "economics_all",
    "map_layout": "status_layout",
    "status_staffing": "status_staff",
}


class NameMap:
    """Validate + resolve a logical ``name`` against an operator ``name_map``."""

    @staticmethod
    def validate(args: dict[str, Any]) -> Optional[str]:
        """Return an ``ERROR:`` string if ``name``/``name_map`` are bad, else ``None``."""
        name = args.get("name")
        if not isinstance(name, str) or not name:
            return "ERROR: invalid_input: 'name' is required."

        raw_map = args.get("name_map")
        if not isinstance(raw_map, dict) or not raw_map:
            return "ERROR: invalid_input: operator must configure 'name_map'; the tool is deny-by-default."

        if name not in raw_map:
            valid = ", ".join(sorted(raw_map.keys()))
            return f"ERROR: unknown_name: '{name}' not in name_map. Valid names: {valid}."

        return None

    @staticmethod
    def resolve_alias(name: str, name_map: dict[str, str]) -> str:
        """Return a canonical mapped name for a known safe synonym."""
        if name in name_map:
            return name
        canonical = SAFE_READ_ALIASES.get(name)
        if canonical in name_map:
            return canonical
        return name
