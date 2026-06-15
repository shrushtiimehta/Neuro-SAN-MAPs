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
Name-based file writer (companion to state_read / state_edit).

The LLM passes a logical ``name`` plus a ``content`` body; the operator
configures the ``name_map`` (``{name: path}``) in HOCON. The tool
resolves the name to a path server-side. Modes:

  - ``overwrite`` (default): replaces the file body.
  - ``append``: appends to the existing file (creates if missing).

Why this instead of path-based write_file: the LLM never sees a path,
so it cannot typo, escape the directory tree, or hallucinate. Only
explicitly-named files are writable.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_management.name_map import NameMap


class StateWrite(CodedTool):
    """Write a file resolved by its operator-configured logical name."""

    MAX_BODY_BYTES: ClassVar[int] = 10 * 1024 * 1024  # 10 MB
    VALID_MODES: ClassVar[frozenset[str]] = frozenset({"overwrite", "append"})

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        Resolve ``name`` via ``name_map`` and write ``content``.

        :param args: dict with keys
            - ``name`` (str, required): logical name; must be a key of
              the operator-supplied ``name_map``.
            - ``content`` (str, required): body to write.
            - ``mode`` (str, optional): ``overwrite`` (default) or ``append``.
            - ``name_map`` (dict, OPERATOR-ONLY): merged from HOCON.
        :param sly_data: ignored.
        :return: dict ``{"status": "ok", "name", "file_path",
            "bytes_written", "mode"}`` or an ``"ERROR: ..."`` string.
        """
        del sly_data

        validation_error = self._validate(args)
        if validation_error is not None:
            return validation_error

        name = args["name"]
        name_map: dict[str, str] = args["name_map"]
        file_path = name_map[name]
        content: str = args["content"]
        mode = (args.get("mode") or "overwrite").strip().lower()

        try:
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        except OSError as err:
            self.logger.error("Could not create parent dir for %s: %s", file_path, err)
            return f"ERROR: Could not create parent dir for {file_path}: {err}"

        file_mode = "a" if mode == "append" else "w"
        try:
            with open(file_path, file_mode, encoding="utf-8") as handle:
                handle.write(content)
        except OSError as err:
            self.logger.error("Could not write %s: %s", file_path, err)
            return f"ERROR: could_not_write: {file_path}: {err}"

        return {
            "status": "ok",
            "name": name,
            "file_path": file_path,
            "bytes_written": len(content.encode("utf-8")),
            "mode": mode,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)

    def _validate(self, args: dict[str, Any]) -> str | None:
        """Return an ``ERROR:`` string on first failure or ``None``."""
        name_map_error = NameMap.validate(args)
        if name_map_error is not None:
            return name_map_error

        content = args.get("content")
        if not isinstance(content, str):
            return "ERROR: invalid_input: 'content' must be a string."

        if len(content.encode("utf-8")) > self.MAX_BODY_BYTES:
            return f"ERROR: body_too_large: content exceeds {self.MAX_BODY_BYTES} bytes."

        mode = (args.get("mode") or "overwrite").strip().lower()
        if mode not in self.VALID_MODES:
            return f"ERROR: invalid_input: 'mode' must be one of {sorted(self.VALID_MODES)}."

        return None
