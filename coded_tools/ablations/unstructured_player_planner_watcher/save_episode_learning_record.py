"""Save what worked and what failed for one free-form episode."""

from __future__ import annotations

import re
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.state_dir import state_path


class SaveEpisodeLearningRecord(CodedTool):
    """Append an idempotent per-episode section to ``episode_learnings.md``."""

    PATH = state_path("episode_learnings.md")

    @staticmethod
    def _items(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        del sly_data
        try:
            episode = int(args.get("episode"))
            reward = float(args.get("final_reward"))
        except (TypeError, ValueError):
            return "ERROR: episode and final_reward are required numbers"
        worked = self._items(args.get("worked"))
        failed = self._items(args.get("did_not_work"))
        summary = str(args.get("summary", "")).strip()
        if not worked or not failed or not summary:
            return "ERROR: worked, did_not_work, and summary must all be non-empty"

        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items)

        section = (
            f"## Episode {episode}\n\n"
            f"Final reward: {reward:g}\n\n"
            f"### What worked\n\n{bullets(worked)}\n\n"
            f"### What did not work / ruined the run\n\n{bullets(failed)}\n\n"
            f"### Overall learning\n\n{summary}\n"
        )
        body = FileIO.read_text(self.PATH)
        pattern = re.compile(rf"(?ms)^## Episode {episode}\n.*?(?=^## Episode \d+\n|\Z)")
        if pattern.search(body):
            body = pattern.sub(section.rstrip() + "\n", body)
            action = "replaced"
        else:
            prefix = body.rstrip()
            body = (prefix + "\n\n" if prefix else "# Episode Learnings\n\n") + section
            action = "appended"
        try:
            FileIO.write_text(self.PATH, body.rstrip() + "\n")
        except OSError as err:
            return f"ERROR: could not write episode learnings: {err}"
        return {"episode": episode, "action": action, "path": self.PATH}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
