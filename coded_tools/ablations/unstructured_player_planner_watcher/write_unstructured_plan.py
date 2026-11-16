"""Persist one complete free-form episode plan without candidate trials.

The underlying writer is reused only for safe marked-block and champion-snapshot
mechanics. The LLM supplies one ``strategy``; no domain summaries or phased
checklist are accepted from it.
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.write_episode_plan import WriteEpisodePlan


class _UnstructuredEpisodePlanWriter(WriteEpisodePlan):
    """Internal adapter for the ablation that intentionally has no domain plans."""

    REQUIRE_DOMAIN_STRATEGIES = False


class WriteUnstructuredPlan(CodedTool):
    """Write one whole-episode strategy into the coordinator playbook."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        strategy = str(args.get("strategy", "")).strip()
        if not strategy:
            return "ERROR: strategy is required and must be non-empty"
        result = _UnstructuredEpisodePlanWriter().invoke(
            {
                "checklist_items": [
                    "turns 1-100: execute the complete current strategy and adapt to live park evidence"
                ],
                "strategy_summary": strategy,
                "playbook_summaries": {},
            },
            sly_data,
        )
        if isinstance(result, str):
            return result
        return {
            "strategy_written": True,
            "playbook_coordinator_path": result.get("playbook_coordinator_path"),
            "plan_snapshot_written": result.get("plan_snapshot_written"),
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
