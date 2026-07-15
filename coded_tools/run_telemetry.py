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
RunTelemetry: factual record across episodes AND across runs.

Two modes:

1. EPISODE mode (default — pass nothing, or from_episode/max_episodes):
   per-episode rollups of EVERY episode present in the CURRENT run dir
   (logs/maps_park/run.ep<NNN>.jsonl), plus a run-level rollup describing the
   trajectory across those episodes. This is the within-run overview.

2. RUNS mode (pass num_runs, e.g. num_runs=3): per-RUN rollups for the N most
   recent runs — the in-flight current run (top-level run.ep*.jsonl) plus the
   most recent archived runs under logs/maps_park/prior-runs/<id>/. This is the
   evidence base for the macro analyzer's "what worked / what didn't across the
   last few runs" cross-run analysis. A run that is starting fresh (no current
   episodes yet) simply contributes nothing and the prior runs fill the window;
   if fewer than N runs exist, every run found is returned.

It reuses EpisodeTelemetry for parsing each episode file (single source of
truth for how a run.ep*.jsonl row maps to metrics), then derives the trends.
It writes nothing — it is a read-only analysis input.

Returns (EPISODE mode):
  {
    "scope": "episodes",
    "run_episode_count": <int>,            # episodes with committed rows
    "episodes": [                          # one entry per episode, ascending
        {"episode": <int>, "rollup": {...from EpisodeTelemetry...}}, ...
    ],
    "run_rollup": {
        "episodes_present":   [<int>, ...],
        "reward_by_episode":  [{episode, cum_end, reward_total}, ...],
        "value_by_episode":   [{episode, value_start, value_end}, ...],
        "rating_by_episode":  [{episode, rating_end}, ...],
        "rejections_by_episode": [{episode, rejection_count}, ...],
        "actions_by_type_total": {action: count, ...},   # summed over the run
        "best_episode":  {episode, cum_end} | None,       # highest cum_end
        "worst_episode": {episode, cum_end} | None,       # lowest cum_end
        "first_cum_end": <float|None>,
        "last_cum_end":  <float|None>,
        "cum_end_delta_last_vs_first": <float|None>,      # episode-over-episode trend
        "mean_cum_end": <float|None>,
    },
    "exists": <bool>,
  }

Returns (RUNS mode, num_runs given):
  {
    "scope": "runs",
    "runs_analyzed": <int>,                # how many runs are in the window
    "runs": [                              # most-recent first ('current' leads)
      {
        "run_id": "current" | "<dir name>",
        "is_current": <bool>,
        "episode_count": <int>,
        "episodes": [{episode, rollup}, ...],          # ascending, per-episode
        "run_summary": {
            "best_episode":  {episode, cum_end} | None,
            "final_episode": {episode, cum_end} | None,
            "reward_by_episode": [{episode, cum_end, reached_step_100}, ...],
            "actions_by_type_total": {action: count, ...},
            "subtypes_placed_total": {subtype/subclass: count, ...},
            "peak_rides_max": <int>,       # best capacity ceiling reached
            "research_on_step_earliest": <int|None>,
            "rejection_total": <int>,
            "episodes_reaching_step_100": <int>,
        },
      }, ...
    ],
    "cross_run_rollup": {
        "runs_present": ["current", "<id>", ...],       # most-recent first
        "best_cum_by_run": [{run_id, best_cum_end}, ...],
        "best_run":  {run_id, best_cum_end} | None,
        "worst_run": {run_id, best_cum_end} | None,
        "newest_best_cum": <float|None>,                # most-recent run's best
        "oldest_best_cum": <float|None>,                # oldest run's best
        "best_cum_delta_newest_vs_oldest": <float|None>,# are we improving?
        "mean_best_cum": <float|None>,
    },
    "exists": <bool>,
  }
"""

from __future__ import annotations

import glob
import os
import re
from collections import Counter
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.episode_telemetry import EpisodeTelemetry


class RunTelemetry(CodedTool):
    """Per-episode rollups within a run, or per-run rollups across runs."""

    RUN_LOG_DIR: ClassVar[str] = EpisodeTelemetry.RUN_LOG_DIR
    # Archived prior runs live one directory deep under here, each a timestamped
    # folder of run.ep*.jsonl files: logs/maps_park/prior-runs/<id>/run.ep*.jsonl
    PRIOR_RUNS_SUBDIR: ClassVar[str] = "prior-runs"
    DEFAULT_NUM_RUNS: ClassVar[int] = 5

    # SELECT mode: per-step fields kept for the two fed episodes. Drops the
    # low-signal/noisy fields (x, y, min_cleanliness, min_uptime, shop_revenue,
    # ride_op_cost) and the heavy rollups entirely — the macro reads raw steps.
    SELECT_KEEP_FIELDS: ClassVar[tuple[str, ...]] = (
        "step", "action", "subtype", "subclass", "price", "rejected_action",
        "error", "reward", "cumulative_reward", "cash", "park_value",
        "park_rating", "research_speed", "num_rides", "num_shops", "num_staff",
    )

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args:
            RUNS mode (cross-run): 'num_runs' (int; the N most recent runs to
              compare — current + prior, default 3) or scope='runs'.
            EPISODE mode (within current run, the default): 'from_episode'
              (int; only episodes >= this) and 'max_episodes' (int; keep only
              the most recent N episodes after the from_episode filter).
        :param sly_data: ignored.
        :return: cross-run telemetry (RUNS mode) or cross-episode telemetry
            (EPISODE mode); see module docstring.
        """
        del sly_data
        scope = str(args.get("scope") or "").strip().lower()
        select = str(args.get("select") or "").strip().lower()
        # SELECT mode takes priority: the best-ever episode, with or without the
        # most-recent one alongside it. 'best'/'best_only' omits last_episode —
        # the micro already has the current episode from EpisodeTelemetry.
        if select in ("best", "best_only"):
            return self._select_mode(include_last=False)
        if select in ("best_and_last", "best_last") or scope == "select":
            return self._select_mode(include_last=True)
        if scope == "runs" or args.get("num_runs") is not None:
            num_runs = FileIO.to_int(args.get("num_runs")) or self.DEFAULT_NUM_RUNS
            return self._runs_mode(max(1, num_runs))
        return self._episodes_mode(args)

    # ── EPISODE mode (within the current run) ───────────────────────────────
    def _episodes_mode(self, args: dict[str, Any]) -> dict[str, Any]:
        from_episode = FileIO.to_int(args.get("from_episode")) if args.get("from_episode") is not None else None
        max_episodes = FileIO.to_int(args.get("max_episodes")) if args.get("max_episodes") is not None else None

        episode_numbers = self._episode_numbers()
        if from_episode is not None:
            episode_numbers = [e for e in episode_numbers if e >= from_episode]
        if max_episodes is not None and max_episodes > 0:
            episode_numbers = episode_numbers[-max_episodes:]

        telemetry = EpisodeTelemetry()
        episodes: list[dict[str, Any]] = []
        for ep in episode_numbers:
            record = telemetry.invoke({"episode": ep}, {})
            if not record.get("exists"):
                continue
            episodes.append({"episode": ep, "rollup": record.get("rollup") or {}})

        if not episodes:
            return {"scope": "episodes", "exists": False, "run_episode_count": 0,
                    "episodes": [], "run_rollup": {}}

        return {
            "scope": "episodes",
            "exists": True,
            "run_episode_count": len(episodes),
            "episodes": episodes,
            "run_rollup": self._run_rollup(episodes),
        }

    # ── SELECT mode (feed the best-ever + last episode as raw steps) ────────
    def _select_mode(self, include_last: bool = True) -> dict[str, Any]:
        """Scan ALL runs to rank every episode by final cumulative reward, then
        return exactly the two episodes the macro start pass wants:

          - last_episode      — the most recent completed episode.
          - reference_episode — the best-scoring episode EVER (across all runs),
            so the analyst always has a strong exemplar to learn from; if that
            IS the last episode, the SECOND-best instead (always distinct).

        Each is returned as FILTERED raw steps (SELECT_KEEP_FIELDS) with NO
        rollup/aggregation — the analyst reads the moves directly.
        """
        discovered = self._discover_runs()
        # Flatten to a global, most-recent-first list. _discover_runs is
        # most-recent-run-first; within a run, higher episode = more recent.
        flat: list[dict[str, Any]] = []
        for run_id, is_current, ep_files in discovered:
            for ep_num, path in sorted(ep_files, reverse=True):
                flat.append({
                    "run_id": run_id, "is_current": is_current,
                    "episode": ep_num, "path": path,
                    "final_cum": self._final_cum(path),
                })
        if not flat:
            out: dict[str, Any] = {"scope": "select", "exists": False,
                                   "reference_episode": None}
            if include_last:
                out["last_episode"] = None
            return out

        last = flat[0]  # global most-recent episode
        # Rank by final cum desc; episodes with no cum sort last.
        ranked = sorted(
            flat,
            key=lambda e: (e["final_cum"] is not None, e["final_cum"] or 0),
            reverse=True,
        )
        best: dict[str, Any] | None = ranked[0]
        if best["path"] == last["path"]:
            best = ranked[1] if len(ranked) > 1 else None

        result: dict[str, Any] = {
            "scope": "select",
            "exists": True,
            "runs_scanned": len(discovered),
            "episodes_scanned": len(flat),
            "reference_episode": self._select_payload(best) if best else None,
            "note": ("reference_episode is the best-scoring episode across ALL "
                     "runs; the current in-flight episode is excluded when it "
                     "would otherwise rank first. No rollups — raw filtered "
                     "steps only."),
        }
        if include_last:
            result["last_episode"] = self._select_payload(last)
        return result

    def _final_cum(self, path: str) -> float | int | None:
        """Cheap rank key: the episode's final cumulative_reward (last row)."""
        rows = EpisodeTelemetry()._read_rows(path)
        if not rows:
            return None
        rows.sort(key=lambda r: r.get("step") if r.get("step") is not None else 0)
        for r in reversed(rows):
            v = r.get("cumulative_reward")
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return v
        return None

    def _select_payload(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Filtered raw steps for one selected episode (no rollup)."""
        rows = EpisodeTelemetry()._read_rows(entry["path"])
        rows.sort(key=lambda r: r.get("step") if r.get("step") is not None else 0)
        steps: list[dict[str, Any]] = []
        for r in rows:
            step: dict[str, Any] = {}
            for f in self.SELECT_KEEP_FIELDS:
                if f == "error":
                    err = r.get("error")
                    if err:
                        step["error"] = err.get("message") if isinstance(err, dict) else err
                elif r.get(f) is not None:
                    step[f] = r.get(f)
            steps.append(step)
        return {
            "run_id": entry["run_id"],
            "is_current": entry["is_current"],
            "episode": entry["episode"],
            "final_cum": entry["final_cum"],
            "step_count": len(steps),
            "steps": steps,
        }

    # ── RUNS mode (across the N most recent runs) ───────────────────────────
    def _runs_mode(self, num_runs: int) -> dict[str, Any]:
        discovered = self._discover_runs()[:num_runs]
        telemetry = EpisodeTelemetry()
        runs: list[dict[str, Any]] = []
        for run_id, is_current, ep_files in discovered:
            episodes: list[dict[str, Any]] = []
            for ep_num, path in ep_files:
                record = telemetry.invoke({"run_log_path": path}, {})
                if not record.get("exists"):
                    continue
                ep = record.get("episode")
                ep = ep if ep is not None else ep_num
                episodes.append({"episode": ep, "rollup": record.get("rollup") or {}})
            if not episodes:
                continue
            episodes.sort(key=lambda e: e["episode"] if e["episode"] is not None else 0)
            runs.append({
                "run_id": run_id,
                "is_current": is_current,
                "episode_count": len(episodes),
                "episodes": episodes,
                "run_summary": self._run_summary(episodes),
            })

        if not runs:
            return {"scope": "runs", "exists": False, "runs_analyzed": 0,
                    "runs": [], "cross_run_rollup": {}}

        return {
            "scope": "runs",
            "exists": True,
            "runs_analyzed": len(runs),
            "runs": runs,
            "cross_run_rollup": self._cross_run_rollup(runs),
        }

    def _discover_runs(self) -> list[tuple[str, bool, list[tuple[int, str]]]]:
        """Most-recent-first list of (run_id, is_current, [(ep_num, path), ...]).

        The in-flight current run (top-level run.ep*.jsonl) leads, followed by
        archived prior runs under prior-runs/<id>/, newest first. Timestamped
        ids (YYYYMMDD-HHMMSS) sort chronologically by name; we fall back to
        directory mtime so non-timestamped names still order sensibly.
        """
        out: list[tuple[str, bool, list[tuple[int, str]]]] = []

        current = self._episode_files(self.RUN_LOG_DIR)
        if current:
            out.append(("current", True, current))

        prior_root = os.path.join(self.RUN_LOG_DIR, self.PRIOR_RUNS_SUBDIR)
        prior_dirs: list[str] = []
        if os.path.isdir(prior_root):
            prior_dirs = [d for d in glob.glob(os.path.join(prior_root, "*"))
                          if os.path.isdir(d)]
        # Newest first: by dir name (timestamped ids), then mtime as tiebreak.
        prior_dirs.sort(key=lambda d: (os.path.basename(d), os.path.getmtime(d)),
                        reverse=True)
        for d in prior_dirs:
            ep_files = self._episode_files(d)
            if ep_files:
                out.append((os.path.basename(d), False, ep_files))
        return out

    @staticmethod
    def _episode_files(run_dir: str) -> list[tuple[int, str]]:
        """Ascending (episode_number, path) for run.ep*.jsonl directly in run_dir."""
        found: list[tuple[int, str]] = []
        for path in glob.glob(os.path.join(run_dir, "run.ep*.jsonl")):
            match = re.search(r"run\.ep(\d+)\.jsonl$", os.path.basename(path))
            if match:
                found.append((int(match.group(1)), path))
        return sorted(found)

    def _episode_numbers(self) -> list[int]:
        """Every episode number with a run.ep<NNN>.jsonl file, ascending."""
        out: list[int] = []
        for path in glob.glob(os.path.join(self.RUN_LOG_DIR, "run.ep*.jsonl")):
            match = re.search(r"run\.ep(\d+)\.jsonl$", os.path.basename(path))
            if match:
                out.append(int(match.group(1)))
        return sorted(out)

    def _run_rollup(self, episodes: list[dict[str, Any]]) -> dict[str, Any]:
        """Derive cross-episode trends from the per-episode rollups."""
        reward_by_episode: list[dict[str, Any]] = []
        value_by_episode: list[dict[str, Any]] = []
        rating_by_episode: list[dict[str, Any]] = []
        rejections_by_episode: list[dict[str, Any]] = []
        actions_total: Counter = Counter()

        for entry in episodes:
            ep = entry["episode"]
            rollup = entry.get("rollup") or {}
            reward_by_episode.append({
                "episode": ep,
                "cum_end": rollup.get("cum_end"),
                "reward_total": rollup.get("reward_total"),
            })
            value_by_episode.append({
                "episode": ep,
                "value_start": rollup.get("value_start"),
                "value_end": rollup.get("value_end"),
            })
            rating_by_episode.append({"episode": ep, "rating_end": rollup.get("rating_end")})
            rejections_by_episode.append({
                "episode": ep,
                "rejection_count": rollup.get("rejection_count"),
            })
            for action, count in (rollup.get("actions_by_type") or {}).items():
                actions_total[action] += count

        # cum_end-based run trend (only over episodes that report a cum_end).
        cum_points = [(r["episode"], r["cum_end"]) for r in reward_by_episode
                      if r["cum_end"] is not None]
        best = worst = None
        first_cum = last_cum = delta = mean_cum = None
        if cum_points:
            best_ep, best_val = max(cum_points, key=lambda p: p[1])
            worst_ep, worst_val = min(cum_points, key=lambda p: p[1])
            best = {"episode": best_ep, "cum_end": best_val}
            worst = {"episode": worst_ep, "cum_end": worst_val}
            first_cum = cum_points[0][1]
            last_cum = cum_points[-1][1]
            delta = round(last_cum - first_cum, 2)
            mean_cum = round(sum(v for _, v in cum_points) / len(cum_points), 2)

        return {
            "episodes_present": [e["episode"] for e in episodes],
            "reward_by_episode": reward_by_episode,
            "value_by_episode": value_by_episode,
            "rating_by_episode": rating_by_episode,
            "rejections_by_episode": rejections_by_episode,
            "actions_by_type_total": dict(actions_total),
            "best_episode": best,
            "worst_episode": worst,
            "first_cum_end": first_cum,
            "last_cum_end": last_cum,
            "cum_end_delta_last_vs_first": delta,
            "mean_cum_end": mean_cum,
        }

    def _run_summary(self, episodes: list[dict[str, Any]]) -> dict[str, Any]:
        """Per-run headline derived from its episode rollups: best/final episode,
        the capacity ceiling reached, earliest research, and how many episodes
        actually ran the full 100-day horizon. This is what the analyst reads to
        judge 'what worked' in a run without scanning every episode."""
        actions_total: Counter = Counter()
        subtypes_total: Counter = Counter()
        reward_by_episode: list[dict[str, Any]] = []
        cum_points: list[tuple[Any, float]] = []
        peak_rides_max = 0
        rejection_total = 0
        research_on_steps: list[int] = []
        reached_100 = 0

        for entry in episodes:
            ep = entry["episode"]
            r = entry.get("rollup") or {}
            cum_end = r.get("cum_end")
            reward_by_episode.append({
                "episode": ep, "cum_end": cum_end,
                "reached_step_100": r.get("reached_step_100"),
            })
            if cum_end is not None:
                cum_points.append((ep, cum_end))
            for action, count in (r.get("actions_by_type") or {}).items():
                actions_total[action] += count
            for sub, count in (r.get("subtypes_placed") or {}).items():
                subtypes_total[sub] += count
            peak_rides_max = max(peak_rides_max, FileIO.to_int(r.get("peak_rides")) or 0)
            rejection_total += FileIO.to_int(r.get("rejection_count")) or 0
            if r.get("research_on_step") is not None:
                research_on_steps.append(r["research_on_step"])
            if r.get("reached_step_100"):
                reached_100 += 1

        best = worst_final = None
        if cum_points:
            best_ep, best_val = max(cum_points, key=lambda p: p[1])
            best = {"episode": best_ep, "cum_end": best_val}
        final_episode = None
        last = episodes[-1]
        final_episode = {"episode": last["episode"],
                         "cum_end": (last.get("rollup") or {}).get("cum_end")}
        return {
            "best_episode": best,
            "final_episode": final_episode,
            "reward_by_episode": reward_by_episode,
            "actions_by_type_total": dict(actions_total),
            "subtypes_placed_total": dict(subtypes_total),
            "peak_rides_max": peak_rides_max,
            "research_on_step_earliest": min(research_on_steps) if research_on_steps else None,
            "rejection_total": rejection_total,
            "episodes_reaching_step_100": reached_100,
        }

    def _cross_run_rollup(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        """Compare runs by their best-episode score (a run's potential ceiling),
        most-recent first, so the analyst can see whether successive runs are
        improving, flat, or regressing."""
        best_cum_by_run: list[dict[str, Any]] = []
        points: list[tuple[str, float]] = []
        for run in runs:
            best = (run.get("run_summary") or {}).get("best_episode")
            best_cum = best.get("cum_end") if best else None
            best_cum_by_run.append({"run_id": run["run_id"], "best_cum_end": best_cum})
            if best_cum is not None:
                points.append((run["run_id"], best_cum))

        best_run = worst_run = None
        newest = oldest = delta = mean_best = None
        if points:
            br_id, br_val = max(points, key=lambda p: p[1])
            wr_id, wr_val = min(points, key=lambda p: p[1])
            best_run = {"run_id": br_id, "best_cum_end": br_val}
            worst_run = {"run_id": wr_id, "best_cum_end": wr_val}
            # runs are most-recent-first, so points[0] is newest.
            newest = points[0][1]
            oldest = points[-1][1]
            delta = round(newest - oldest, 2)
            mean_best = round(sum(v for _, v in points) / len(points), 2)

        return {
            "runs_present": [r["run_id"] for r in runs],
            "best_cum_by_run": best_cum_by_run,
            "best_run": best_run,
            "worst_run": worst_run,
            "newest_best_cum": newest,
            "oldest_best_cum": oldest,
            "best_cum_delta_newest_vs_oldest": delta,
            "mean_best_cum": mean_best,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        return self.invoke(args, sly_data)
