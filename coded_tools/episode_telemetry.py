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
EpisodeTelemetry: structured per-step factual record for one episode,
read directly from the deterministic run.jsonl the runner writes.

This replaces the LLM-authored turn_notes journal as the evidence base
for the consultant network's learning loop. run.jsonl rows are written
by the runner's _append_run_jsonl_row (apps/maps_park/runner.py), which
spreads the dispatched action's args (subtype, subclass, price, x, y)
into each row alongside the post-step metrics — so this tool can surface
both WHAT was done and its measured effect, without parsing free-text.

The trial_analyst/curator judge trials by reading `steps` — the faithful
per-step run (full action args incl. x/y, plus metrics) — and `rejections`
to decide whether a trial's intended move actually fired, plus the per-step
reward/value deltas for success/failure. `applied` is a lossy convenience
digest (non-wait actions only, no coords/metrics); do not judge from it.

Returns:
  {
    "episode":  <int>,
    "steps":    [ {step, action, type, subtype, subclass, price,
                   order_quantity, x, y, reward,
                   cumulative_reward, cash, park_value, park_rating,
                   research_speed, num_rides, num_shops, num_staff,
                   min_cleanliness, min_uptime, shop_revenue,
                   ride_op_cost}, ... ],   # sorted by step
    "applied":  [ {step, action, subtype, subclass}, ... ],  # non-wait actions
    "rejections": [ {step, rejected_action, subtype, subclass, price,
                     error}, ... ],  # actions the sim refused (logged as wait)
    "rollup":   { step_count, first_step, last_step, reached_step_100,
                  reward_total, cum_start, cum_end, value_start, value_end,
                  cash_end, rating_end, actions_by_type, subtypes_placed,
                  research_speeds_used, research_on_step, peak_rides,
                  peak_shops, peak_staff, reward_bands, rejection_count,
                  rejections_by_action },
    "exists":   <bool>,
  }

A rejected proposal is committed as an `action="wait"` row carrying the
original `rejected_action` (e.g. "modify") plus an `error` describing why
(e.g. "Invalid ticket price: 6. Max ticket price: 4"). These are the only
record that the agent TRIED something and the sim refused it — surface them
so the learning loop can diagnose repeated wrong-action attempts (e.g. using
`modify` to change a tier) rather than only seeing a stream of waits.
"""

from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO


class EpisodeTelemetry(CodedTool):
    """Read one episode's per-episode run log and return its structured record.

    The runner writes one file per episode (logs/maps_park/run.ep<NNN>.jsonl)
    and is the sole writer, so a file contains exactly one episode's committed
    post-step rows  no tool-name filtering needed.
    """

    RUN_LOG_DIR: ClassVar[str] = "logs/maps_park"

    # Metric fields copied verbatim from each run.jsonl row.
    METRIC_FIELDS: ClassVar[tuple[str, ...]] = (
        "reward", "cumulative_reward", "cash", "park_value", "park_rating",
        "research_speed", "num_rides", "num_shops", "num_staff",
        "min_cleanliness", "min_uptime", "shop_revenue", "ride_op_cost",
    )
    # Action fields the runner spreads into the row from the dispatched args.
    # Carry the FULL applied-action shape (coords, quantity, type included) so
    # `steps` is the faithful run the close-out judge reads to decide whether a
    # trial's intended move actually fired — not the lossy `applied` digest.
    ACTION_FIELDS: ClassVar[tuple[str, ...]] = (
        "type", "subtype", "subclass", "price", "order_quantity", "x", "y")

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args: optional 'episode' (int; default = latest episode in
            the log), 'from_step' (int; only return steps >= this, for
            mid-episode periodic calls), 'run_log_path' (override).
        :param sly_data: ignored.
        :return: structured per-episode telemetry (see module docstring).
        """
        del sly_data
        # Resolve which episode's file to read.
        episode = FileIO.to_int(args.get("episode")) if args.get("episode") is not None else None
        path = args.get("run_log_path")
        if path:
            path = str(path)
        elif episode is not None:
            path = self._episode_path(episode)
        else:
            episode, path = self._latest_episode()

        if not path or not os.path.exists(path):
            return {"exists": False, "episode": episode, "steps": [],
                    "applied": [], "rollup": {},
                    "error": f"run log not found: {path}"}

        ep_rows = self._read_rows(path)
        if not ep_rows:
            return {"exists": False, "episode": episode, "steps": [],
                    "applied": [], "rollup": {},
                    "error": f"no committed rows in {path}"}

        if episode is None:
            episode = next((r.get("episode") for r in ep_rows
                            if r.get("episode") is not None), None)

        from_step = FileIO.to_int(args.get("from_step")) if args.get("from_step") is not None else None

        ep_rows.sort(key=lambda r: (r.get("step") if r.get("step") is not None else 0))

        steps: list[dict[str, Any]] = []
        for r in ep_rows:
            step = r.get("step")
            if from_step is not None and step is not None and step < from_step:
                continue
            entry: dict[str, Any] = {"step": step, "action": r.get("action")}
            for f in self.ACTION_FIELDS:
                if r.get(f) is not None:
                    entry[f] = r.get(f)
            # Surface a refused proposal: the row is committed as a wait but
            # carries rejected_action + error explaining what was refused.
            if r.get("rejected_action") is not None:
                entry["rejected_action"] = r.get("rejected_action")
            err = r.get("error")
            if err:
                entry["error"] = err.get("message") if isinstance(err, dict) else err
            for f in self.METRIC_FIELDS:
                entry[f] = r.get(f)
            steps.append(entry)

        applied = [
            {"step": s["step"], "action": s["action"],
             "subtype": s.get("subtype"), "subclass": s.get("subclass")}
            for s in steps
            if s["action"] not in (None, "wait")
        ]

        rejections = [
            {"step": s["step"], "rejected_action": s.get("rejected_action"),
             "subtype": s.get("subtype"), "subclass": s.get("subclass"),
             "price": s.get("price"), "error": s.get("error")}
            for s in steps
            if s.get("rejected_action") is not None or s.get("error")
        ]

        return {
            "exists": True,
            "episode": episode,
            "steps": steps,
            "applied": applied,
            "rejections": rejections,
            "rollup": self._rollup(steps),
        }

    def _episode_path(self, episode: int) -> str:
        return os.path.join(self.RUN_LOG_DIR, f"run.ep{episode:03d}.jsonl")

    def _latest_episode(self) -> tuple[int | None, str | None]:
        """Highest-numbered episode file present (episode, path)."""
        best: tuple[int, str] | None = None
        for p in glob.glob(os.path.join(self.RUN_LOG_DIR, "run.ep*.jsonl")):
            m = re.search(r"run\.ep(\d+)\.jsonl$", os.path.basename(p))
            if m:
                ep = int(m.group(1))
                if best is None or ep > best[0]:
                    best = (ep, p)
        return best if best is not None else (None, None)

    def _read_rows(self, path: str) -> list[dict[str, Any]]:
        """Committed post-step rows from one episode file (real step only).

        The runner is the sole writer, so every row is authoritative; we
        only skip rows missing a step (defensive).
        """
        rows: list[dict[str, Any]] = []
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("step") is None:
                        continue
                    rows.append(row)
        except OSError:
            return []
        return rows

    def _rollup(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        if not steps:
            return {}
        actions_by_type: Counter = Counter()
        subtypes_placed: Counter = Counter()
        rejections_by_action: Counter = Counter()
        research_speeds: list[Any] = []
        reward_total = 0.0
        rejection_count = 0
        peak_rides = peak_shops = peak_staff = 0
        research_on_step: int | None = None
        for s in steps:
            if s.get("action"):
                actions_by_type[s["action"]] += 1
            if s.get("action") == "place" and s.get("subtype"):
                key = s["subtype"]
                if s.get("subclass"):
                    key = f"{s['subtype']}/{s['subclass']}"
                subtypes_placed[key] += 1
            if s.get("rejected_action") is not None:
                rejection_count += 1
                rejections_by_action[s["rejected_action"]] += 1
            rspeed = s.get("research_speed")
            if rspeed and rspeed != "none":
                if rspeed not in research_speeds:
                    research_speeds.append(rspeed)
                if research_on_step is None and s.get("step") is not None:
                    research_on_step = s.get("step")
            reward_total += FileIO.to_float(s.get("reward"))
            peak_rides = max(peak_rides, FileIO.to_int(s.get("num_rides")) or 0)
            peak_shops = max(peak_shops, FileIO.to_int(s.get("num_shops")) or 0)
            peak_staff = max(peak_staff, FileIO.to_int(s.get("num_staff")) or 0)
        first, last = steps[0], steps[-1]
        last_step = last.get("step")
        return {
            "step_count": len(steps),
            "first_step": first.get("step"),
            "last_step": last_step,
            # An episode is the full 100-day horizon; anything short ended early
            # (cash crash / cut off) and never reaches the back-half harvest.
            "reached_step_100": bool(last_step is not None and last_step >= 100),
            "reward_total": round(reward_total, 2),
            "cum_start": first.get("cumulative_reward"),
            "cum_end": last.get("cumulative_reward"),
            "value_start": first.get("park_value"),
            "value_end": last.get("park_value"),
            "cash_end": last.get("cash"),
            "rating_end": last.get("park_rating"),
            "actions_by_type": dict(actions_by_type),
            "subtypes_placed": dict(subtypes_placed),
            "research_speeds_used": research_speeds,
            # First step research left 'none'. Late/never => under-investment.
            "research_on_step": research_on_step,
            # Capacity ceiling: only rides drive guest throughput, so the peak
            # ride count is the dominant cap on the back-half revenue engine.
            "peak_rides": peak_rides,
            "peak_shops": peak_shops,
            "peak_staff": peak_staff,
            # Avg reward/step in fixed 25-step bands: the compounding curve.
            # A healthy episode ramps hard in the 76-100 band (the harvest).
            "reward_bands": self._reward_bands(steps),
            "rejection_count": rejection_count,
            "rejections_by_action": dict(rejections_by_action),
        }

    @staticmethod
    def _reward_bands(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Average reward/step in four fixed step bands (1-25, 26-50, 51-75,
        76-100), each with the band's end park_value / park_rating. Surfaces
        the compounding curve so the analyst can see whether (and when) an
        episode took off, without re-reading every per-step row."""
        bounds = [(1, 25), (26, 50), (51, 75), (76, 100)]
        bands: list[dict[str, Any]] = []
        for lo, hi in bounds:
            in_band = [s for s in steps
                       if s.get("step") is not None and lo <= s["step"] <= hi]
            if not in_band:
                continue
            total = sum(FileIO.to_float(s.get("reward")) for s in in_band)
            last = in_band[-1]
            bands.append({
                "band": f"{lo}-{hi}",
                "steps": len(in_band),
                "avg_reward_per_step": round(total / len(in_band), 1),
                "end_value": last.get("park_value"),
                "end_rating": last.get("park_rating"),
            })
        return bands

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        return self.invoke(args, sly_data)
