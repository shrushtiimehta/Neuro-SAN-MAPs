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
Shared file-IO and value-coercion helpers for coded tools.

Before this module, every coded tool that touched a file or coerced an
argument carried its own private copy of the same boilerplate: ``_int`` /
``_coerce_int`` / ``_num`` integer-float coercion, ``_append`` / ``_write``
/ ``_write_file`` / ``_write_body`` open-and-write blocks, ``_read_body``
read-with-size-cap blocks, and ``os.makedirs(os.path.dirname(path), ...)``.
These drifted (e.g. three subtly different ``_int`` implementations), so
they are consolidated here as a single set of static helpers.

This module is deliberately MCP-agnostic: it does not touch the simulator
transport (``maps_action_base``), only local files and plain Python values.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from typing import Optional


class FileIO:
    """Stateless file-IO and coercion helpers shared across coded tools.

    Every method is a ``@staticmethod``; ``FileIO`` is a namespace, not an
    object to instantiate.
    """

    # ----- value coercion -------------------------------------------------

    @staticmethod
    def to_int(value: Any, default: Optional[int] = None) -> Optional[int]:
        """``int(value)`` or ``default`` when it cannot be coerced.

        ``int()`` already strips surrounding whitespace from strings, so
        this also covers the ``int(str(value).strip())`` variant that
        ``AdvanceEpisode`` previously used for regex-parsed phase fields.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def to_float(value: Any, default: float = 0.0) -> float:
        """``float(value)`` or ``default`` when it cannot be coerced."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    # ----- directory / write ---------------------------------------------

    @staticmethod
    def ensure_parent(path: str) -> None:
        """Create the parent directory of ``path`` if it has one."""
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    @staticmethod
    def write_text(path: str, content: str) -> None:
        """Overwrite ``path`` with ``content`` (creating parents).

        Raises ``OSError`` on failure; callers that need an ``ERROR:``
        string instead should use :meth:`write_guarded`.
        """
        FileIO.ensure_parent(path)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    @staticmethod
    def append_text(path: str, content: str) -> None:
        """Append ``content`` to ``path`` (creating parents).

        Empty ``content`` is a no-op (no file is created). Raises
        ``OSError`` on failure.
        """
        if not content:
            return
        FileIO.ensure_parent(path)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(content)

    @staticmethod
    def write_guarded(
        path: str, content: str, logger: Optional[logging.Logger] = None
    ) -> Optional[str]:
        """Overwrite ``path``; return ``None`` on success or an ``ERROR:`` string.

        The error-string convention (rather than raising) mirrors the
        coded-tool tools whose ``invoke`` returns ``"ERROR: ..."`` to the
        caller.
        """
        try:
            FileIO.write_text(path, content)
            return None
        except OSError as err:
            if logger is not None:
                logger.error("Could not write %s: %s", path, err)
            return f"ERROR: could_not_write: {path}: {err}"

    # ----- read -----------------------------------------------------------

    @staticmethod
    def read_text(path: str, default: str = "") -> str:
        """Return the file body, or ``default`` when missing/unreadable."""
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return default

    @staticmethod
    def read_capped(
        path: str, max_bytes: int, logger: Optional[logging.Logger] = None
    ) -> str:
        """Return the file body, or a descriptive ``ERROR:`` string.

        Distinct from :meth:`read_text`: surfaces ``file_not_found`` /
        ``file_too_large`` / ``could_not_read`` as ``ERROR:`` strings and
        enforces ``max_bytes``. Used by the name-mapped state tools.
        """
        if not os.path.exists(path):
            return f"ERROR: file_not_found: {path}."
        try:
            size = os.path.getsize(path)
        except OSError as err:
            return f"ERROR: could_not_stat: {path}: {err}"
        if size > max_bytes:
            return f"ERROR: file_too_large: {path} exceeds {max_bytes} bytes."
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as err:
            if logger is not None:
                logger.error("Could not read %s: %s", path, err)
            return f"ERROR: could_not_read: {path}: {err}"
