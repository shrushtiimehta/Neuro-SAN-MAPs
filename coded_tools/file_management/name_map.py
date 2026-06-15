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

StateRead, StateWrite and StateEdit all carried an identical block that
validated the logical ``name`` against the operator-supplied ``name_map``
(deny-by-default) and resolved it to a path. That block lives here now so
the three tools cannot drift apart.
"""

from __future__ import annotations

from typing import Any
from typing import Optional


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
