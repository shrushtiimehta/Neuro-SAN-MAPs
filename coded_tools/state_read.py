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
Name-based file reader.

The LLM never sees a file path. The operator configures a ``name_map``
in HOCON (``{name: absolute_or_relative_path}``); the LLM passes a
``name`` and the tool resolves it server-side. Unknown name -> error.

Why: passing raw paths through the LLM is fragile (typos, hallucinated
directories, '..' escapes). With ``name_map``, only explicitly listed
files are addressable, and the name surface is small and semantic
('playbook_rides', 'trial_strategies') rather than path-shaped.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.name_map import NameMap


class StateRead(CodedTool):
    """Read a file by its operator-configured logical name."""

    MAX_BODY_BYTES: ClassVar[int] = 10 * 1024 * 1024  # 10 MB
    DEFAULT_MAX_CHARS: ClassVar[int] = 20000

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        Resolve ``name`` to a path via ``name_map`` and read the file.

        :param args: dict with keys
            - ``name`` (str, required): logical name; must be a key of
              the operator-supplied ``name_map``.
            - ``start_line`` (int, optional): 1-based start line.
            - ``end_line`` (int, optional): 1-based inclusive end line.
            - ``max_content_chars`` (int, optional): cap on returned
              characters (default 20000).
            - ``name_map`` (dict, OPERATOR-ONLY): merged from HOCON.
              Required (deny-by-default).
        :param sly_data: ignored.
        :return: dict with ``status``, ``name``, ``file_path`` (echoed
            for log readability), ``content``, ``line_count``,
            ``truncated`` on success, or an ``"ERROR: ..."`` string.
        """
        del sly_data

        validation_error = NameMap.validate(args)
        if validation_error is not None:
            return validation_error

        name = args["name"]
        name_map: dict[str, str] = args["name_map"]
        file_path = name_map[name]

        body_or_error = FileIO.read_capped(file_path, self.MAX_BODY_BYTES, self.logger)
        if isinstance(body_or_error, str) and body_or_error.startswith("ERROR:"):
            return body_or_error
        body: str = body_or_error

        start_line = args.get("start_line")
        end_line = args.get("end_line")
        max_chars = int(args.get("max_content_chars") or self.DEFAULT_MAX_CHARS)

        sliced, total_lines = self._slice_lines(body, start_line, end_line)
        truncated = False
        if len(sliced) > max_chars:
            sliced = sliced[:max_chars]
            truncated = True

        return {
            "status": "ok",
            "name": name,
            "file_path": file_path,
            "content": sliced,
            "line_count": total_lines,
            "truncated": truncated,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)

    def _slice_lines(self, body: str, start_line: Any, end_line: Any) -> tuple[str, int]:
        """Slice body to the inclusive line range, returning (sliced, total_lines)."""
        lines = body.splitlines(keepends=True)
        total = len(lines)
        start_idx = FileIO.to_int(start_line, 1) - 1
        end_idx = FileIO.to_int(end_line, total)
        start_idx = max(0, start_idx)
        end_idx = min(total, end_idx)
        if start_idx >= end_idx:
            return ("", total)
        return ("".join(lines[start_idx:end_idx]), total)
