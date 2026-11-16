"""Load immutable baseline guidance into live GMemory state once."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore


class GMemorySeed(CodedTool):
    """Initialize read-only base guidance without writing Markdown state files."""

    DOMAINS = ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
    CONFIG_DIR = Path(__file__).resolve().parents[2] / "config_files"

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """Copy baseline text to the live database on first use or fresh reset."""
        del sly_data
        store = GMemoryStore()
        overwrite = bool(args.get("overwrite", False))
        seeded: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []
        for domain in self.DOMAINS:
            name = f"baseline_{domain}"
            if not overwrite and store.get(name):
                skipped.append(f"playbook_{domain}")
                continue
            source = self.CONFIG_DIR / f"seed_playbook_{domain}.md"
            try:
                body = source.read_text(encoding="utf-8")
            except OSError as error:
                errors.append(f"{source}: {error}")
                continue
            # Only hand-authored baseline instructions are seeded. Learned rules
            # from other arms must never leak into this ablation.
            body = re.sub(
                r"<!-- (?:STRATEGY|PLAYBOOK)_SUMMARY:BEGIN -->.*?"
                r"<!-- (?:STRATEGY|PLAYBOOK)_SUMMARY:END -->",
                "",
                body,
                flags=re.DOTALL,
            )
            body = "\n".join(line for line in body.splitlines() if "(learned ep" not in line) + "\n"
            if store.seed(name, body, overwrite=overwrite):
                seeded.append(f"playbook_{domain}")
            else:
                skipped.append(f"playbook_{domain}")
        return {"status": "ok", "seeded": seeded, "skipped": skipped, "errors": errors, "trial_ledgers_created": []}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the same seed operation for asynchronous tool calls."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
