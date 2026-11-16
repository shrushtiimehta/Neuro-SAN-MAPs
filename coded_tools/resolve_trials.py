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
ResolveTrials: apply the curator's per-trial report to the trial files at
episode end, deterministically.

Policy (per active trial):
  - confirmed / falsified -> REMOVE from trial_strategies + trial_strategies_criteria
  - not_applied / inconclusive -> KEEP
  - every reportable active trial requires exactly one explicit verdict
  - inconclusive requires a non-empty evidence note
  - origin=micro -> REMOVE regardless of outcome (micro trials are episode-scoped;
    a confirmed one was already promoted to the playbook by the curator), so the
    next episode starts back at just the persisted macro trials.
  - a macro trial older than ActiveTrials still serves, absent from the report
    -> REMOVE as 'expired'. It cannot be reported on, because ActiveTrials no
    longer shows it to the close-out; keeping it as 'inconclusive' would leave a
    trial that is both invisible and undeletable.
For every MACRO trial (never micro — those are written for one episode's exact
state and teach the next planner nothing) append one line to
trial_strategies_outcome, carrying the rule TEXT as well as its id (the id's
rule is deleted from trial_strategies in the same call, so this line is the only
surviving record of what was tried):
  "- OUTCOME ep=<N> trial_id=<id> domain=<D> origin=<O> outcome=<O> note='<note>' rule='<text>'"
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.active_trials import ActiveTrials
from coded_tools.file_io import FileIO
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import OUTCOME_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import filter_lines
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies
from coded_tools.trial_parsing import read_text


class ResolveTrials(CodedTool):
    """Trim trial_strategies + criteria and append outcomes from the curator report."""

    REMOVE_OUTCOMES = frozenset({"confirmed", "falsified"})
    VALID_OUTCOMES = frozenset({"confirmed", "falsified", "not_applied", "inconclusive"})
    _OUTCOME_KEY_RE = re.compile(r"\bep=(?P<episode>-?\d+)\s+trial_id=(?P<trial_id>\S+)")

    @staticmethod
    def _pending_path() -> str:
        """Journal beside the active trial ledger for crash-safe replay."""
        return os.path.join(os.path.dirname(STRATEGIES_PATH), ".resolve_trials.pending.json")

    @classmethod
    def _apply_pending(cls, payload: dict[str, Any]) -> str | None:
        """Finish a journaled resolution. Reapplying the post-state is safe."""
        try:
            post = payload["post"]
            FileIO.write_text_atomic(OUTCOME_PATH, str(post["outcomes"]))
            FileIO.write_text_atomic(STRATEGIES_PATH, str(post["strategies"]))
            # Criteria is published last. ActiveTrials iterates strategy ids, so
            # an interruption before this write leaves either the full old active
            # set or the full new active set; extra old criteria are harmless.
            FileIO.write_text_atomic(CRITERIA_PATH, str(post["criteria"]))
            try:
                os.remove(cls._pending_path())
            except FileNotFoundError:
                pass
            return None
        except (KeyError, TypeError, OSError) as err:
            return f"ERROR: could not commit trial resolution: {err}"

    @classmethod
    def _recover_pending(cls) -> tuple[dict[str, Any] | None, str | None]:
        """Complete an interrupted prior call before accepting another report."""
        path = cls._pending_path()
        if not os.path.exists(path):
            return None, None
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as err:
            return None, f"ERROR: could not read pending trial resolution: {err}"
        error = cls._apply_pending(payload)
        return payload, error

    @staticmethod
    def _normalize_report(raw_report: Any) -> list[dict[str, Any]] | None:
        """Accept native arrays plus common wrappers emitted by tool-calling LLMs.

        Older schemas described ``report`` as a JSON string. Depending on the
        provider, that arrived as a native list, a fenced JSON string, a single
        object, or ``{"report": [...]}``. All carry the same information and
        should not terminate a completed episode.
        """
        if raw_report is None or raw_report == "":
            return []
        report = raw_report
        if isinstance(report, str):
            text = report.strip()
            if text.startswith("```") and text.endswith("```"):
                lines = text.splitlines()
                if len(lines) >= 2:
                    text = "\n".join(lines[1:-1]).strip()
            try:
                report = json.loads(text)
            except json.JSONDecodeError:
                return None
        if isinstance(report, dict):
            key: Any
            for key in ("report", "trials", "results"):
                if isinstance(report.get(key), list):
                    report = report[key]
                    break
            else:
                report = [report] if report.get("trial_id") else None
        if not isinstance(report, list) or any(not isinstance(entry, dict) for entry in report):
            return None
        return report

    @classmethod
    def _validate_report(cls, report: list[dict[str, Any]], required_ids: list[str]) -> str | None:
        """Require one well-formed verdict for every reportable active trial."""
        reported_ids: set[str] = set()
        duplicate_ids: set[str] = set()
        index: Any
        entry: Any
        for index, entry in enumerate(report):
            trial_id = str(entry.get("trial_id", "")).strip()
            if not trial_id:
                return f"ERROR: report entry {index} is missing trial_id"
            outcome = str(entry.get("outcome", "")).strip().lower()
            if outcome not in cls.VALID_OUTCOMES:
                allowed = ", ".join(sorted(cls.VALID_OUTCOMES))
                return f"ERROR: trial {trial_id} has invalid outcome {outcome!r}; expected one of: {allowed}"
            if outcome == "inconclusive" and not str(entry.get("note", "")).strip():
                return f"ERROR: trial {trial_id} is inconclusive but has no evidence note"
            if trial_id in reported_ids:
                duplicate_ids.add(trial_id)
            reported_ids.add(trial_id)

        if duplicate_ids:
            return f"ERROR: duplicate trial verdicts: {', '.join(sorted(duplicate_ids))}"

        required = set(required_ids)
        missing = sorted(required - reported_ids)
        unknown = sorted(reported_ids - required)
        problems: list[str] = []
        if missing:
            problems.append(f"missing verdicts: {', '.join(missing)}")
        if unknown:
            problems.append(f"unknown or unreportable trial ids: {', '.join(unknown)}")
        if problems:
            return "ERROR: incomplete trial report; " + "; ".join(problems)
        return None

    @staticmethod
    def _too_old(crit: dict[str, Any], episode: int) -> bool:
        """True when ActiveTrials would no longer serve this trial.

        Deliberately reads the SAME constant ActiveTrials filters on: if the two
        rules ever drift apart, trials reappear in the gap between them —
        withheld from every reader, yet never resolved away.
        """
        try:
            return int(crit.get("ep")) < episode - ActiveTrials.MAX_CARRYOVER_EPISODES
        except (TypeError, ValueError):
            return False  # unparseable ep -> treat as current, never expire blind

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: episode (int); report (JSON list of
            {trial_id, domain, outcome, note}).
        :return: {kept:[...], removed:[...], outcomes_appended:N} or "ERROR: ...".
        """
        del sly_data
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"

        recovered, recovery_error = self._recover_pending()
        if recovery_error:
            return recovery_error
        if recovered is not None and int(recovered.get("episode", -1)) == episode:
            result = recovered.get("result")
            if isinstance(result, dict):
                return result

        strat_text = read_text(STRATEGIES_PATH)
        crit_text = read_text(CRITERIA_PATH)
        strategies = parse_strategies(strat_text)
        active_ids = list(strategies.keys())
        criteria = parse_criteria(crit_text)

        # With no active trials there is nothing to resolve. Historically an
        # LLM sometimes sent prose such as "no active trials" here; rejecting
        # that after a successful 100-step episode killed the whole run.
        report = self._normalize_report(args.get("report")) if active_ids else []
        if report is None:
            return "ERROR: report must be an array of per-trial objects (native JSON array or JSON-encoded array)"
        required_ids = [trial_id for trial_id in active_ids if not self._too_old(criteria.get(trial_id, {}), episode)]
        report_error = self._validate_report(report, required_ids)
        if report_error:
            return report_error
        report_map = {str(entry["trial_id"]).strip(): entry for entry in report}

        keep_ids: set[str] = set()
        kept: list[str] = []
        removed: list[str] = []
        outcome_lines: list[str] = []

        trial_id: Any
        for trial_id in active_ids:
            entry = report_map.get(trial_id)
            crit = criteria.get(trial_id, {})
            origin = crit.get("origin", "")
            if entry:
                outcome = str(entry["outcome"]).strip().lower()
                note = str(entry.get("note", "")).strip()
                domain = entry.get("domain") or crit.get("domain", "")
            else:
                outcome, note = "inconclusive", "no_report"
                domain = crit.get("domain", "")

            # micro trials are episode-scoped — drop every one regardless of
            # outcome (a confirmed one was already promoted by the curator) so the
            # next episode starts back at just the persisted macro trials.
            if origin == "micro" and outcome not in self.REMOVE_OUTCOMES:
                note = (f"{note}; " if note else "") + "micro_episode_scoped"

            # A macro trial too old to still be served is unreportable: ActiveTrials
            # withholds it, so the close-out never sees it, so it is never confirmed
            # or falsified — and "inconclusive" would KEEP it. Left alone that is a
            # trial which is both invisible and undeletable. Expire it here, where
            # the raw ledger is still in view.
            if not entry and origin != "micro" and self._too_old(crit, episode):
                outcome = "expired"
                note = (f"{note}; " if note else "") + (
                    f"stranded since ep{crit.get('ep')} — no close-out ever resolved it"
                )

            if outcome in self.REMOVE_OUTCOMES or origin == "micro" or outcome == "expired":
                removed.append(trial_id)
            else:
                keep_ids.add(trial_id)
                kept.append(trial_id)
            # MACRO ONLY. A micro rule is written for one episode's exact state
            # ("from steps 61-70, if cash is at least 8500 and num_rides is 13...")
            # and is meaningless once that park is gone, so its outcome is not
            # ledgered — it would only teach the next planner about a park that
            # no longer exists. The removal above still happens either way.
            if origin == "micro":
                continue
            # The rule TEXT goes in the line, not just its id. The next episode's
            # planner reads this ledger to avoid re-proposing a falsified idea —
            # and "t1_1 falsified" tells it nothing, because the id's rule is
            # deleted from trial_strategies.md in the same call.
            rule = (strategies.get(trial_id) or "").replace("'", "").strip()
            outcome_lines.append(
                f"- OUTCOME ep={episode} trial_id={trial_id} domain={domain} "
                f"origin={origin} outcome={outcome} note='{note}' rule='{rule}'\n"
            )

        existing_outcomes = read_text(OUTCOME_PATH)
        existing_keys = {
            (int(match.group("episode")), match.group("trial_id"))
            for match in self._OUTCOME_KEY_RE.finditer(existing_outcomes)
        }
        unique_outcome_lines = [
            line
            for line in outcome_lines
            if (episode, self._OUTCOME_KEY_RE.search(line).group("trial_id")) not in existing_keys
        ]
        result = {
            "kept": kept,
            "removed": removed,
            "outcomes_appended": len(unique_outcome_lines),
        }
        payload = {
            "version": 1,
            "episode": episode,
            "post": {
                "strategies": filter_lines(strat_text, keep_ids),
                "criteria": filter_lines(crit_text, keep_ids),
                "outcomes": existing_outcomes + "".join(unique_outcome_lines),
            },
            "result": result,
        }
        try:
            FileIO.write_text_atomic(self._pending_path(), json.dumps(payload, sort_keys=True) + "\n")
        except OSError as err:
            return f"ERROR: could not journal trial resolution: {err}"
        commit_error = self._apply_pending(payload)
        if commit_error:
            return commit_error
        return result

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
