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
Name-based in-place string-replace editor.

Companion to state_read / state_write. Caller passes a logical ``name``,
``find_text`` and ``new_text``; the tool resolves the name via the
operator ``name_map`` and applies the substitution atomically (read,
replace, write).

Semantics mirror EditFile: by default ``find_text`` must occur exactly
once (zero -> ``not_found``, more than one -> ``ambiguous``). Set
``replace_all=true`` to swap every occurrence.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.file_io import FileIO
from coded_tools.file_management.name_map import NameMap


class StateEdit(CodedTool):
    """Surgical substring replacement on a name-resolved file."""

    MAX_FILE_BYTES: ClassVar[int] = 10 * 1024 * 1024  # 10 MB

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        Resolve ``name`` via ``name_map`` and apply a string-replace edit.

        :param args: dict with keys
            - ``name`` (str, required): logical name; must be a key of
              the operator-supplied ``name_map``.
            - ``find_text`` (str, required): exact substring to find.
            - ``new_text`` (str, required): replacement.
            - ``replace_all`` (bool, optional, default ``false``).
            - ``name_map`` (dict, OPERATOR-ONLY): merged from HOCON.
        :param sly_data: ignored.
        :return: dict ``{"status": "ok", "name", "file_path",
            "replacements"}`` or an ``"ERROR: ..."`` string.
        """
        del sly_data

        validation_error = self._validate(args)
        if validation_error is not None:
            return validation_error

        name = args["name"]
        name_map: dict[str, str] = args["name_map"]
        file_path = name_map[name]
        find_text: str = args["find_text"]
        new_text: str = args["new_text"]
        replace_all = bool(args.get("replace_all", False))

        body_or_error = FileIO.read_capped(file_path, self.MAX_FILE_BYTES, self.logger)
        if isinstance(body_or_error, str) and body_or_error.startswith("ERROR:"):
            return body_or_error
        body: str = body_or_error

        count = body.count(find_text)
        if count == 0:
            return f"ERROR: not_found: find_text was not present in {name}."
        if count > 1 and not replace_all:
            return (
                f"ERROR: ambiguous: find_text appeared {count} times in {name}; "
                f"pass replace_all=true or provide a longer find_text."
            )

        if replace_all:
            new_body = body.replace(find_text, new_text)
            replacements = count
        else:
            new_body = body.replace(find_text, new_text, 1)
            replacements = 1

        write_error = FileIO.write_guarded(file_path, new_body, self.logger)
        if write_error is not None:
            return write_error

        return {
            "status": "ok",
            "name": name,
            "file_path": file_path,
            "replacements": replacements,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)

    def _validate(self, args: dict[str, Any]) -> str | None:
        """Return an ``ERROR:`` string on first failure or ``None``."""
        name_map_error = NameMap.validate(args)
        if name_map_error is not None:
            return name_map_error

        find_text = args.get("find_text")
        if not isinstance(find_text, str) or find_text == "":
            return "ERROR: invalid_input: 'find_text' must be a non-empty string."

        new_text = args.get("new_text")
        if not isinstance(new_text, str):
            return "ERROR: invalid_input: 'new_text' must be a string."

        return None
