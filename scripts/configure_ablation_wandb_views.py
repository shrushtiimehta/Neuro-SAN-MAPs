#!/usr/bin/env python3
"""Configure one detailed W&B workspace for run and episode exploration."""

from __future__ import annotations

import argparse

import wandb_workspaces.expr as expr
import wandb_workspaces.reports.v2 as wr
import wandb_workspaces.workspaces as ws

DEFAULT_WORKSPACE_URL = "https://wandb.ai/shrushtm-cognizant/maps-park-ablations?nw=ryoiz4i75ee"


def line(title: str, x: str, *metrics: str) -> wr.LinePlot:
    """Create a consistently configured line panel."""
    return wr.LinePlot(title=title, x=x, y=list(metrics))


def scalar(title: str, metric: str) -> wr.ScalarChart:
    """Create a scalar card for one episode-level value."""
    return wr.ScalarChart(title=title, metric=metric)


def instructions() -> ws.Section:
    return ws.Section(
        name="How to Use This Dashboard",
        is_open=True,
        panels=[
            wr.MarkdownPanel(
                markdown=(
                    "## Run and episode navigation\n\n"
                    "Expand **Ablation → Run** in the run selector.\n\n"
                    "- Select **Ablation • Run N** for episode-wise run metrics.\n"
                    "- Select **Ablation • Run N • Episode N** for that episode's "
                    "step-by-step and turn-by-turn metrics.\n"
                    "- Episode numbers start at **1**. Trajectory steps retain their "
                    "recorded **1–100** values.\n\n"
                    "Run panels and episode panels use separate metric namespaces so "
                    "only the relevant charts appear for the selected entry."
                )
            )
        ],
    )


def run_outcomes() -> ws.Section:
    return ws.Section(
        name="Run — Episode Outcomes",
        is_open=True,
        panels=[
            line(
                "Cumulative Reward by Episode",
                "run/episode",
                "run/cumulative_reward",
            ),
            wr.ScalarChart(
                title="Average Cumulative Reward",
                metric="run/cumulative_reward.mean",
            ),
            wr.ScalarChart(
                title="Max Cumulative Reward",
                metric="run/cumulative_reward.max",
            ),
            line("Recorded Steps per Episode", "run/episode", "run/episode_steps"),
            line("Episode Completion", "run/episode", "run/episode_complete"),
        ],
    )


def run_park_state() -> ws.Section:
    return ws.Section(
        name="Run — Final Park State by Episode",
        is_open=True,
        panels=[
            line("Final Cash", "run/episode", "run/episode_final/cash"),
            line(
                "Final Park Value",
                "run/episode",
                "run/episode_final/park_value",
            ),
            line(
                "Final Park Rating",
                "run/episode",
                "run/episode_final/park_rating",
            ),
            line(
                "Final Assets and Staff",
                "run/episode",
                "run/episode_final/num_rides",
                "run/episode_final/num_shops",
                "run/episode_final/num_staff",
            ),
            line(
                "Final Uptime and Cleanliness",
                "run/episode",
                "run/episode_final/min_uptime",
                "run/episode_final/min_cleanliness",
            ),
            line(
                "Final Revenue and Operating Cost",
                "run/episode",
                "run/episode_final/shop_revenue",
                "run/episode_final/ride_op_cost",
            ),
            line("Recorded Park Value", "run/episode", "run/park/final_value"),
        ],
    )


def run_usage() -> ws.Section:
    return ws.Section(
        name="Run — Model Usage by Episode",
        is_open=True,
        panels=[
            line("Tokens", "run/episode", "run/episode_cost/tokens"),
            line("LLM Calls", "run/episode", "run/episode_cost/llm_calls"),
            line("LLM Time", "run/episode", "run/episode_cost/llm_seconds"),
            line(
                "Usage Record Completeness",
                "run/episode",
                "run/episode_cost/cost_complete",
                "run/episode_cost/cost_is_estimate",
            ),
        ],
    )


def episode_result() -> ws.Section:
    return ws.Section(
        name="Episode — Result and Usage",
        is_open=True,
        panels=[
            scalar("Final Cumulative Reward", "cumulative_reward"),
            scalar("Episode Tokens", "episode_cost/tokens"),
            scalar("Episode LLM Calls", "episode_cost/llm_calls"),
            scalar("Episode LLM Time", "episode_cost/llm_seconds"),
            scalar("Recorded Park Value", "park/final_value"),
        ],
    )


def episode_progress() -> ws.Section:
    return ws.Section(
        name="Episode — Progress Across Steps 1–100",
        is_open=True,
        panels=[
            line(
                "Cumulative Reward",
                "step",
                "cumulative_reward",
            ),
            line("Step Reward", "step", "reward"),
            line("Cash", "step", "cash"),
            line("Park Value", "step", "park_value"),
            line("Park Rating", "step", "park_rating"),
        ],
    )


def episode_operations() -> ws.Section:
    return ws.Section(
        name="Episode — Park Operations Across Steps",
        is_open=True,
        panels=[
            line(
                "Assets and Staff",
                "step",
                "num_rides",
                "num_shops",
                "num_staff",
            ),
            line(
                "Uptime and Cleanliness",
                "step",
                "min_uptime",
                "min_cleanliness",
            ),
            line(
                "Revenue and Operating Cost",
                "step",
                "shop_revenue",
                "ride_op_cost",
            ),
        ],
    )


def episode_turns() -> ws.Section:
    return ws.Section(
        name="Episode — Turn and Model Usage",
        is_open=False,
        panels=[
            line("Attempts by Turn", "turn/number", "turn/attempts"),
            line(
                "Tokens by Turn",
                "turn/number",
                "total_tokens",
                "prompt_tokens",
                "completion_tokens",
            ),
            line(
                "Requests by Turn",
                "turn/number",
                "turn/tokens/successful_requests",
                "turn/tokens/empty_responses",
            ),
            line(
                "LLM Time by Turn",
                "turn/number",
                "turn/tokens/time_taken_in_seconds",
            ),
        ],
    )


def dashboard_sections() -> list[ws.Section]:
    """Return sections in run-first, episode-second reading order."""
    return [
        instructions(),
        run_outcomes(),
        run_park_state(),
        run_usage(),
        episode_result(),
        episode_progress(),
        episode_operations(),
        episode_turns(),
    ]


def runset() -> ws.RunsetSettings:
    return ws.RunsetSettings(
        filters="JobType = 'ablation' or JobType = 'episode'",
        groupby=[expr.Config("Ablation"), expr.Config("Run")],
        order=[
            expr.Ordering(expr.Config("Episode"), ascending=True),
            expr.Ordering(expr.Metric("Name"), ascending=True),
        ],
        pinned_columns=["run:displayName"],
    )


def configure(url: str) -> ws.Workspace:
    workspace = ws.Workspace.from_url(url)
    workspace.name = "Ablation Results"
    workspace.runset_settings = runset()
    workspace.sections = dashboard_sections()
    return workspace.save()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-url", default=DEFAULT_WORKSPACE_URL)
    args = parser.parse_args()
    workspace = configure(args.workspace_url)
    print(f"Workspace: {workspace.url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
