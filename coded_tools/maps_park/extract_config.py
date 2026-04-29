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
ExtractConfig: per-domain MAPs knowledge reader.

Inspired by the airline_policy ``ExtractDocs`` pattern. A specialist agent
calls this tool with a ``domain`` argument and gets back BOTH:

1. ``yaml_content`` — the economic constants for that domain
   (rides_economics.yaml, shops_economics.yaml, etc.) including the
   field-meaning glossary at the top of the file.
2. ``notes_content`` — the qualitative game-mechanics notes for the same
   domain (rides_notes.md, shops_notes.md, etc.).

Returning raw text (rather than parsed YAML) preserves the comment
glossaries so the LLM can read the field definitions inline.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool


class ExtractConfig(CodedTool):
    """Reads one MAPs domain's YAML config + Markdown notes by domain name."""

    def __init__(self):
        config_dir = "coded_tools/maps_park/config_files"

        # Numeric / structured config (per-tier costs, rates, capacities, ...).
        self.yaml_paths: dict[str, str] = {
            "rides":    f"{config_dir}/rides_economics.yaml",
            "shops":    f"{config_dir}/shops_economics.yaml",
            "staff":    f"{config_dir}/staff_economics.yaml",
            "research": f"{config_dir}/research_economics.yaml",
            "world":    f"{config_dir}/world_constants.yaml",
        }

        # Qualitative game-mechanics notes (rules, tips, subclass effects).
        self.notes_paths: dict[str, str] = {
            "rides":    f"{config_dir}/rides_notes.md",
            "shops":    f"{config_dir}/shops_notes.md",
            "staff":    f"{config_dir}/staff_notes.md",
            "research": f"{config_dir}/research_notes.md",
            "world":    f"{config_dir}/world_notes.md",
        }

        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args:
            - "domain" (str): one of rides, shops, staff, research, world.
        :return: dict with keys ``domain``, ``yaml_path``, ``yaml_content``,
            ``notes_path``, ``notes_content`` on success, or an
            ``"ERROR: ..."`` string on failure.
        """
        domain = args.get("domain")
        if not domain:
            return self._format_unknown_domain_error(None)

        yaml_path = self.yaml_paths.get(domain)
        notes_path = self.notes_paths.get(domain)
        if yaml_path is None or notes_path is None:
            return self._format_unknown_domain_error(domain)

        yaml_content = self._read_text(yaml_path)
        if isinstance(yaml_content, str) and yaml_content.startswith("ERROR:"):
            return yaml_content

        notes_content = self._read_text(notes_path)
        if isinstance(notes_content, str) and notes_content.startswith("ERROR:"):
            return notes_content

        return {
            "domain": domain,
            "yaml_path": yaml_path,
            "yaml_content": yaml_content,
            "notes_path": notes_path,
            "notes_content": notes_content,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Delegates to the synchronous invoke method."""
        return self.invoke(args, sly_data)

    def _read_text(self, path: str) -> str:
        """Read a file as raw text. Returns ``"ERROR: ..."`` on failure."""
        if not os.path.exists(path):
            self.logger.error("Config file not found: %s", path)
            return f"ERROR: File not found at {path}."

        try:
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as err:
            self.logger.error("Could not read %s: %s", path, err)
            return f"ERROR: Could not read {path}: {err}"

    def _format_unknown_domain_error(self, domain: str | None) -> str:
        valid = ", ".join(sorted(self.yaml_paths.keys()))
        if domain is None:
            return f"ERROR: No domain provided. Choose one of: {valid}."
        return f"ERROR: Unknown domain {domain!r}. Choose one of: {valid}."
