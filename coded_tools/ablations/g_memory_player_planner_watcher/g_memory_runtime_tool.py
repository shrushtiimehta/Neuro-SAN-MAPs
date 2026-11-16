"""Live plan and trial operations for the GMemory ablation."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from coded_tools.active_trials import _current_episode
from coded_tools.resolve_trials import ResolveTrials


class GMemoryRuntimeTool(ResolveTrials):
    """Handle the existing tool contracts without runtime Markdown files."""

    DOMAINS = frozenset({"coordinator", "rides", "shops", "staff", "research", "layout", "survey"})

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Dispatch the operator-bound operation for this tool instance."""
        del sly_data
        operation = str(args.get("memory_operation", ""))
        store = GMemoryStore()
        operations = {
            "scratchpad": self._scratchpad,
            "log_trial": self._log_trial,
            "active_trials": self._active_trials,
            "delete_trial": self._delete_trial,
            "carryover_trials": self._carryover_trials,
            "resolve_trials": self._resolve_trials,
            "promote_trial": self._promote_trial,
        }
        handler = operations.get(operation)
        return handler(store, args) if handler else f"ERROR: unknown GMemory live operation: {operation}"

    def _scratchpad(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any]:
        """Keep exactly one note per agent until its next invocation."""
        pad = re.sub(r"[^a-z0-9_]", "", str(args.get("pad") or "player").lower()) or "player"
        key = f"scratchpad_{pad}"
        note = str(args.get("note") or "").strip()
        if note:
            trimmed = "\n".join(note.splitlines()[:5])[:600]
            store.put(key, trimmed)
            return {"status": "ok", "action": "wrote", "pad": key, "note": trimmed}
        return {"status": "ok", "action": "read_and_cleared", "pad": key, "note": store.pop(key)}

    # Explicit field errors are part of the existing LogTrial tool contract.
    # pylint: disable=too-many-return-statements
    def _log_trial(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any] | str:
        """Validate and atomically store a trial rule with its criteria."""
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"
        origin = str(args.get("origin", "")).strip().lower()
        if origin not in {"micro", "macro"}:
            return "ERROR: origin must be 'micro' or 'macro'"
        edit_type = str(args.get("edit_type", "")).strip()
        if edit_type not in {"add_line", "replace_line"}:
            return "ERROR: edit_type must be 'add_line' or 'replace_line'"
        fields = ("new_text", "domain", "section", "rationale", "success_criterion", "failure_criterion")
        values = {field: str(args.get(field, "")).strip() for field in fields}
        for field, value in values.items():
            if not value:
                return f"ERROR: {field} is required and must be non-empty"
        find_text = str(args.get("find_text", "")).strip()
        if edit_type == "replace_line" and not find_text:
            return "ERROR: replace_line requires find_text"
        step = args.get("step_start")
        if step != "end_of_episode":
            try:
                step = int(step)
            except (TypeError, ValueError):
                return "ERROR: step_start must be an integer or 'end_of_episode'"
        payload = {
            "rule": values.get("new_text"),
            "domain": values.get("domain"),
            "origin": origin,
            "section": values.get("section"),
            "rationale": values.get("rationale"),
            "success_criterion": values.get("success_criterion"),
            "failure_criterion": values.get("failure_criterion"),
            "edit_type": edit_type,
            "find_text": find_text,
            "step_start": step,
        }
        return {"trial_id": store.log_trial(episode, payload)}

    def _active_trials(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any]:
        """Filter active rules by domain, origin, and one-episode carryover age."""
        domain = str(args.get("domain") or "").strip().lower()
        origin = str(args.get("trial_origin") or "").strip().lower()
        episode = _current_episode()
        all_trials = store.trials()
        stale = [
            str(trial.get("trial_id"))
            for trial in all_trials
            if episode is not None and int(trial.get("ep", episode)) < episode - 1
        ]
        trials = [
            trial
            for trial in all_trials
            if str(trial.get("trial_id")) not in stale
            and (not domain or domain == "all" or trial.get("domain") == domain)
            and (origin not in {"micro", "macro"} or trial.get("origin") == origin)
        ]
        return {
            "domain": domain or "all",
            "origin": origin or "all",
            "count": len(trials),
            "trials": trials,
            "stale_withheld": stale,
        }

    def _delete_trial(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any] | str:
        """Prune one micro trial without recording an outcome."""
        trial_id = str(args.get("trial_id", "")).strip()
        if not trial_id:
            return "ERROR: trial_id is required and must be non-empty"
        trial = next((row for row in store.trials() if row.get("trial_id") == trial_id), None)
        if trial is None:
            return f"ERROR: unknown or already-removed trial_id: {trial_id}"
        if trial.get("origin") != "micro":
            return f"ERROR: refusing to delete non-micro trial_id: {trial_id}"
        store.retire([trial_id])
        return {"deleted": trial_id}

    def _carryover_trials(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any] | str:
        """Give prior-episode rules to one planning pass, then retire them."""
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"
        carried = [trial for trial in store.trials() if int(trial.get("ep", episode)) < episode]
        ids = [str(trial.get("trial_id")) for trial in carried]
        outcomes = [
            {
                "episode": episode,
                "trial_id": trial.get("trial_id"),
                "domain": trial.get("domain"),
                "origin": trial.get("origin"),
                "outcome": "carried_over",
                "note": f"fed to episode {episode} planner and retired",
                "rule": trial.get("rule"),
            }
            for trial in carried
        ]
        store.record_outcomes(episode, outcomes, ids)
        return {"episode": episode, "count": len(carried), "trials": carried, "cleared": ids}

    # Keep verdict variables together so resolution matches the canonical tool.
    # pylint: disable=too-many-locals
    def _resolve_trials(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any] | str:
        """Apply canonical report validation and persist verdicts atomically."""
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"
        trials = store.trials()
        report = self._normalize_report(args.get("report")) if trials else []
        if report is None:
            return "ERROR: report must be an array of per-trial objects (native JSON array or JSON-encoded array)"
        required = [
            str(trial.get("trial_id")) for trial in trials if not self._too_old({"ep": trial.get("ep")}, episode)
        ]
        error = self._validate_report(report, required)
        if error:
            return error
        reported = {str(entry.get("trial_id", "")).strip(): entry for entry in report}
        kept: list[str] = []
        removed: list[str] = []
        outcomes: list[dict[str, Any]] = []
        for trial in trials:
            trial_id = str(trial.get("trial_id"))
            entry = reported.get(trial_id)
            origin = str(trial.get("origin"))
            verdict = str(entry.get("outcome", "")).strip().lower() if entry else "inconclusive"
            note = str(entry.get("note", "")).strip() if entry else "no_report"
            if not entry and origin != "micro" and self._too_old({"ep": trial.get("ep")}, episode):
                verdict = "expired"
            if origin == "micro" or verdict in self.REMOVE_OUTCOMES or verdict == "expired":
                removed.append(trial_id)
            else:
                kept.append(trial_id)
            outcomes.append(
                {
                    "episode": episode,
                    "trial_id": trial_id,
                    "domain": entry.get("domain", trial.get("domain")) if entry else trial.get("domain"),
                    "origin": origin,
                    "outcome": verdict,
                    "note": note,
                    "rule": trial.get("rule"),
                }
            )
        written = store.record_outcomes(episode, outcomes, removed)
        return {"kept": kept, "removed": removed, "outcomes_appended": written, "memory_backend": "gmemory"}

    # Keep add, replace, and demotion policy together for one atomic rule update.
    # pylint: disable=too-many-branches
    def _promote_trial(self, store: GMemoryStore, args: dict[str, Any]) -> dict[str, Any] | str:
        """Keep confirmed rules available now and in the completed trajectory."""
        domain = str(args.get("domain", "")).strip().lower()
        if domain not in self.DOMAINS:
            return f"ERROR: domain must be one of {sorted(self.DOMAINS)}"
        edit_type = str(args.get("edit_type", "")).strip()
        if edit_type not in {"add_line", "replace_line", "remove_line"}:
            return "ERROR: edit_type must be add_line, replace_line, or remove_line"
        key = f"promoted_{domain}"
        rules = json.loads(store.get(key) or "[]")
        suppressed_key = f"suppressed_{domain}"
        suppressed = json.loads(store.get(suppressed_key) or "[]")
        replacements_key = f"replacements_{domain}"
        replacements = json.loads(store.get(replacements_key) or "{}")
        if edit_type == "remove_line":
            find_text = str(args.get("find_text", "")).strip()
            matches = [rule for rule in rules if find_text and find_text in rule]
            if len(matches) != 1:
                action = "skipped_not_found" if not matches else "skipped_ambiguous"
                return {"action_taken": action, "playbook": f"gmemory:{domain}", "line": ""}
            rules.remove(matches[0])
            line = matches[0]
            original = replacements.pop(line, None)
            if original in suppressed:
                suppressed.remove(original)
            action = "demoted"
        else:
            line = str(args.get("new_text", "")).strip()
            if not line:
                return "ERROR: new_text is required and must be non-empty"
            if edit_type == "replace_line" and line not in rules:
                find_text = str(args.get("find_text", "")).strip()
                if not find_text:
                    return "ERROR: replace_line requires find_text"
                candidates = [rule for rule in rules if find_text in rule]
                candidates.extend(
                    baseline_line
                    for baseline_line in (store.get(f"baseline_{domain}") or "").splitlines()
                    if find_text in baseline_line and baseline_line not in suppressed
                )
                if len(candidates) != 1:
                    action = "skipped_not_found" if not candidates else "skipped_ambiguous"
                    return {"action_taken": action, "playbook": f"gmemory:{domain}", "line": line}
                original = candidates[0]
                if original in rules:
                    rules.remove(original)
                else:
                    suppressed.append(original)
                replacements[line] = original
            action = "already_promoted" if line in rules else "promoted"
            if line not in rules:
                rules.append(line)
        store.put(key, json.dumps(rules))
        store.put(suppressed_key, json.dumps(suppressed))
        store.put(replacements_key, json.dumps(replacements))
        return {
            "action_taken": action,
            "playbook": f"gmemory:{domain}",
            "line": line,
            "seed_mirror": "not_applicable_gmemory",
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Execute the same live operation for asynchronous tool calls."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
