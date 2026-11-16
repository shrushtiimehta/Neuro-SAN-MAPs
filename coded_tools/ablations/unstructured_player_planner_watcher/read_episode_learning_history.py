"""Read the append-only free-form episode learning journal."""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.state_dir import state_path


class ReadEpisodeLearningHistory(CodedTool):
    PATH = state_path("episode_learnings.md")
    MAX_CHARS = 100_000

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        del sly_data
        if str(args.get("scope", "")).strip().lower() != "all":
            return "ERROR: scope is required and must be 'all'"
        body = FileIO.read_text(self.PATH)
        truncated = len(body) > self.MAX_CHARS
        if truncated:
            body = body[-self.MAX_CHARS :]
        return {"exists": bool(body), "content": body, "truncated": truncated}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
