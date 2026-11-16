#!/usr/bin/env python3
"""Recover Baseline Run 19's complete trial lifecycle from old tool transcripts."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs/thinking_dir-old"
RUN_DIR = ROOT / "logs/maps_park/prior-runs/20260820-234115"
START = datetime.fromisoformat("2026-08-19 23:30:00")
END = datetime.fromisoformat("2026-08-20 23:27:19")
PAIR = re.compile(
    r"\[AGENT\] @ (?P<received>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):\n"
    r"Received arguments:\n```json\n(?P<args>.*?)\n```\n\n"
    r"\[AGENT\] @ (?P<returned>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d):\n"
    r"Got result:\n```json\n(?P<result>.*?)\n```",
    re.DOTALL,
)
REWARDS = [
    437459,
    662771,
    1501444,
    450861,
    754574,
    445019,
    681863,
    909396,
    622802,
    1165773,
    1104339,
]


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=ROOT / "artifacts/baseline_run19_trial_audit.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=ROOT / "artifacts/baseline_run19_trial_audit.md",
    )
    return parser.parse_args()


def transcript_events(prefix: str, event_type: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for path in sorted(LOG_DIR.glob(f"{prefix}*")):
        if not path.is_file():
            continue
        for index, match in enumerate(PAIR.finditer(path.read_text(encoding="utf-8"))):
            stamp = datetime.fromisoformat(match.group("received"))
            if not START <= stamp <= END:
                continue
            try:
                received = json.loads(match.group("args"))
                returned = json.loads(match.group("result"))
            except json.JSONDecodeError:
                continue
            events.append(
                {
                    "event_type": event_type,
                    "timestamp": stamp.isoformat(sep=" "),
                    "source_file": str(path.resolve()),
                    "source_event_index": index,
                    "arguments": received.get("tool_args", received),
                    "result": returned.get("tool_output", returned),
                    "tool_error": returned.get("tool_error", False),
                }
            )
    return events


def collect() -> dict[str, list[dict[str, Any]]]:
    groups = {
        "macro_proposals": transcript_events("macro_orchestrator.episode_start.LogTrial", "macro_proposal"),
        "micro_proposals": transcript_events("mid_episode_analyst.LogTrial", "micro_proposal"),
        "deletions": transcript_events("mid_episode_analyst.DeleteTrial", "deletion"),
        "resolutions": transcript_events("macro_orchestrator.episode_end.ResolveTrials", "resolution"),
        "promotions": transcript_events("macro_orchestrator.episode_end.PromoteTrial", "promotion"),
        "carryovers": transcript_events("macro_orchestrator.episode_start.CarryoverTrials", "carryover"),
    }
    for values in groups.values():
        values.sort(key=lambda item: (item["timestamp"], item["source_file"]))
    return groups


def proposal_rows(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for kind in ("macro_proposals", "micro_proposals"):
        for serial, event in enumerate(groups[kind], 1):
            args = event["arguments"]
            result = event["result"]
            rows.append(
                {
                    "proposal_serial": f"p{len(rows) + 1:03d}",
                    "timestamp": event["timestamp"],
                    "source_file": event["source_file"],
                    "source_event_index": event["source_event_index"],
                    "origin": "macro" if kind == "macro_proposals" else "micro",
                    "episode_zero_based": args.get("episode"),
                    "episode": (args.get("episode") + 1) if isinstance(args.get("episode"), int) else None,
                    "trial_id": result.get("trial_id"),
                    "domain": args.get("domain"),
                    "rule": args.get("new_text"),
                    "rationale": args.get("rationale"),
                    "success_criterion": args.get("success_criterion"),
                    "failure_criterion": args.get("failure_criterion"),
                    "step_start": args.get("step_start"),
                    "tool_error": event["tool_error"],
                    "origin_serial": serial,
                }
            )
    rows.sort(key=lambda item: (item["timestamp"], item["origin"], item["origin_serial"]))
    return rows


def resolution_rows(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in groups["resolutions"]:
        args = event["arguments"]
        try:
            report = json.loads(args.get("report", "[]"))
        except json.JSONDecodeError:
            report = []
        for verdict in report:
            rows.append(
                {
                    "timestamp": event["timestamp"],
                    "episode_zero_based": args.get("episode"),
                    "episode": args.get("episode", -1) + 1,
                    "reward": REWARDS[args["episode"]] if args.get("episode") in range(len(REWARDS)) else None,
                    **verdict,
                    "resolve_result": event["result"],
                    "source_file": event["source_file"],
                }
            )
    return rows


def attach_lifecycle(
    proposals: list[dict[str, Any]],
    groups: dict[str, list[dict[str, Any]]],
    resolutions: list[dict[str, Any]],
) -> None:
    timeline: list[tuple[str, int, str, Any]] = []
    for index, proposal in enumerate(proposals):
        timeline.append((proposal["timestamp"], 0, "proposal", index))
    for event in groups["deletions"]:
        timeline.append((event["timestamp"], 1, "deletion", event))
    for index, verdict in enumerate(resolutions):
        timeline.append((verdict["timestamp"], 2, "resolution", index))
    timeline.sort(key=lambda item: (item[0], item[1]))
    active: dict[tuple[int, str], int] = {}
    for _, _, event_type, payload in timeline:
        if event_type == "proposal":
            proposal = proposals[payload]
            key = (proposal["episode_zero_based"], proposal["trial_id"])
            active[key] = payload
            proposal["lifecycle"] = "open"
        elif event_type == "deletion":
            event = payload
            trial_id = event["arguments"].get("trial_id")
            match = next(
                ((key, index) for key, index in reversed(list(active.items())) if key[1] == trial_id),
                None,
            )
            if match:
                key, index = match
                proposal = proposals[index]
                proposal["lifecycle"] = "deleted_before_closeout"
                proposal["delete_timestamp"] = event["timestamp"]
                proposal["delete_tool_outcome"] = event["result"].get("outcome")
                proposal["delete_result"] = event["result"]
                del active[key]
        else:
            verdict = resolutions[payload]
            key = (verdict["episode_zero_based"], verdict["trial_id"])
            index = active.get(key)
            if index is not None:
                proposal = proposals[index]
                proposal["lifecycle"] = "resolved_at_closeout"
                proposal["closeout_outcome"] = verdict["outcome"]
                proposal["closeout_note"] = verdict["note"]
                verdict["proposal_serial"] = proposal["proposal_serial"]
                verdict["rule"] = proposal["rule"]
                verdict["origin"] = proposal["origin"]
                del active[key]


def promotion_rows(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for event in groups["promotions"]:
        args = event["arguments"]
        result = event["result"]
        episode = args.get("episode")
        rows.append(
            {
                "timestamp": event["timestamp"],
                "episode_zero_based": episode,
                "episode": episode + 1 if isinstance(episode, int) else None,
                "reward": REWARDS[episode] if episode in range(len(REWARDS)) else None,
                "domain": args.get("domain"),
                "promoted_rule": args.get("new_text"),
                "action_taken": result.get("action_taken"),
                "playbook": result.get("playbook"),
                "seed_mirror": result.get("seed_mirror"),
                "result": result,
                "source_file": event["source_file"],
            }
        )
    return rows


def carryover_rows(groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for event in groups["carryovers"]:
        episode = event["arguments"].get("episode")
        result = event["result"]
        rows.append(
            {
                "timestamp": event["timestamp"],
                "episode_zero_based": episode,
                "episode": episode + 1 if isinstance(episode, int) else None,
                "trial_ids": [trial.get("trial_id") for trial in result.get("trials", [])],
                "count": result.get("count"),
                "cleared": result.get("cleared"),
                "result": result,
                "source_file": event["source_file"],
            }
        )
    return rows


def episode_summary(proposals: list[dict[str, Any]], resolutions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for episode_zero in range(12):
        episode_proposals = [p for p in proposals if p["episode_zero_based"] == episode_zero]
        episode_verdicts = [r for r in resolutions if r["episode_zero_based"] == episode_zero]
        rows.append(
            {
                "episode": episode_zero + 1,
                "episode_zero_based": episode_zero,
                "status": "complete" if episode_zero < 11 else "partial_at_step_30",
                "reward": REWARDS[episode_zero] if episode_zero < len(REWARDS) else 6753,
                "macro_suggestions": sum(p["origin"] == "macro" for p in episode_proposals),
                "micro_suggestions": sum(p["origin"] == "micro" for p in episode_proposals),
                "deleted_before_closeout": sum(
                    p.get("lifecycle") == "deleted_before_closeout" for p in episode_proposals
                ),
                "confirmed": sum(r["outcome"] == "confirmed" for r in episode_verdicts),
                "falsified": sum(r["outcome"] == "falsified" for r in episode_verdicts),
                "not_applied": sum(r["outcome"] == "not_applied" for r in episode_verdicts),
                "inconclusive": sum(r["outcome"] == "inconclusive" for r in episode_verdicts),
            }
        )
    return rows


def markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Baseline Run 19 trial audit",
        "",
        f"Historical transcript window: `{summary['window']['start']}` through `{summary['window']['end']}` UTC.",
        "Episode numbers in this report are one-based; the raw tools used zero-based episode IDs.",
        "",
        "## What the audit establishes",
        "",
        f"- {summary['macro_suggestions']} macro suggestions and "
        f"{summary['micro_suggestions']} micro suggestions were logged.",
        f"- {summary['deleted_before_closeout']} proposal instances were deleted before closeout. "
        "DeleteTrial returned a `falsified` tool response, but these were not written as durable "
        "ResolveTrials outcomes.",
        f"- The durable closeout ledger contains {summary['resolved_total']} verdicts: "
        f"{summary['closeout_outcomes'].get('confirmed', 0)} confirmed, "
        f"{summary['closeout_outcomes'].get('falsified', 0)} falsified, "
        f"{summary['closeout_outcomes'].get('not_applied', 0)} not applied, and "
        f"{summary['closeout_outcomes'].get('inconclusive', 0)} inconclusive.",
        f"- {summary['successful_unique_promotions']} unique rules were promoted. Every closeout-confirmed "
        "trial led to a successful promotion, even when its episode was far below the 1.501M Run 19 best "
        "or the 1.861M retained champion.",
        f"- {summary['reused_episode_trial_ids']} episode/trial-ID pairs were reused for different proposal "
        f"instances; {summary['proposal_instances_with_reused_ids']} proposal instances therefore have "
        "ambiguous IDs without timestamps.",
        "- Episode 12 was partial (step 30), so its remaining trials have no episode-end verdict.",
        "",
        "## Episode outcome matrix",
        "",
        "| Episode | Status | Reward | Macro | Micro | Deleted | Confirmed | Falsified | Not applied | Inconclusive |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["episodes"]:
        lines.append(
            f"| {row['episode']} | {row['status']} | {row['reward']:,} | "
            f"{row['macro_suggestions']} | {row['micro_suggestions']} | "
            f"{row['deleted_before_closeout']} | {row['confirmed']} | {row['falsified']} | "
            f"{row['not_applied']} | {row['inconclusive']} |"
        )
    lines += [
        "",
        "## Promoted rules and the episode that produced them",
        "",
        "A promotion is a playbook write, not proof that it improved final reward. One call first failed "
        "with `skipped_section_missing` and was retried successfully.",
        "",
        "| Ep | Reward | Domain | Result | Rule |",
        "|---:|---:|---|---|---|",
    ]
    for row in payload["promotions"]:
        rule = (row["promoted_rule"] or "").replace("|", "\\|")
        lines.append(f"| {row['episode']} | {row['reward']:,} | {row['domain']} | {row['action_taken']} | {rule} |")
    lines += [
        "",
        "## All official closeout verdicts",
        "",
        "| Ep | Reward | Trial | Origin | Domain | Verdict | Rule / hypothesis | Evidence note |",
        "|---:|---:|---|---|---|---|---|---|",
    ]
    for row in payload["resolutions"]:
        rule = (row.get("rule") or "[proposal could not be uniquely attached]").replace("|", "\\|")
        note = (row.get("note") or "").replace("|", "\\|")
        lines.append(
            f"| {row['episode']} | {row['reward']:,} | {row['trial_id']} | "
            f"{row.get('origin', '?')} | {row['domain']} | **{row['outcome']}** | {rule} | {note} |"
        )
    lines += [
        "",
        "## Complete proposal-instance ledger",
        "",
        "This appendix keeps every suggestion instance. Repeated trial IDs are intentional evidence of ID reuse "
        "after deletion.",
        "",
        "| Serial | Time | Ep | ID | Origin | Domain | Lifecycle | Hypothesis |",
        "|---|---|---:|---|---|---|---|---|",
    ]
    for row in payload["proposals"]:
        rule = (row.get("rule") or "").replace("|", "\\|")
        lines.append(
            f"| {row['proposal_serial']} | {row['timestamp']} | {row['episode']} | "
            f"{row['trial_id']} | {row['origin']} | {row['domain']} | "
            f"{row.get('lifecycle', 'unknown')} | {rule} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "The closeout notes usually support their narrow telemetry criteria, but they do not establish causal "
        "improvement against a counterfactual. The system promoted local within-window successes from globally "
        "losing episodes. Meanwhile, most strategic suggestions were either never applied or deleted before "
        "closeout, and the crucial ride-capacity/cull experiments repeatedly remained `not_applied`. This is a "
        "learning/execution mismatch, not evidence that those strategies were tested and disproved.",
        "",
        "The JSON companion preserves full rationales, success/failure criteria, raw tool results, carryovers, "
        "timestamps, and source-file paths.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    options = cli()
    groups = collect()
    proposals = proposal_rows(groups)
    resolutions = resolution_rows(groups)
    attach_lifecycle(proposals, groups, resolutions)
    promotions = promotion_rows(groups)
    carryovers = carryover_rows(groups)
    ids = Counter((p["episode_zero_based"], p["trial_id"]) for p in proposals)
    closeout = Counter(row["outcome"] for row in resolutions)
    successful_promotions = [p for p in promotions if p["action_taken"] == "promoted"]
    unique_promotions = {(p["episode_zero_based"], p["domain"], p["promoted_rule"]) for p in successful_promotions}
    payload = {
        "summary": {
            "window": {"start": START.isoformat(sep=" "), "end": END.isoformat(sep=" ")},
            "macro_suggestions": len(groups["macro_proposals"]),
            "micro_suggestions": len(groups["micro_proposals"]),
            "total_suggestions": len(proposals),
            "delete_calls": len(groups["deletions"]),
            "deleted_before_closeout": sum(p.get("lifecycle") == "deleted_before_closeout" for p in proposals),
            "resolved_total": len(resolutions),
            "closeout_outcomes": dict(closeout),
            "promotion_calls": len(promotions),
            "successful_promotion_calls": len(successful_promotions),
            "successful_unique_promotions": len(unique_promotions),
            "carryover_calls": len(carryovers),
            "reused_episode_trial_ids": sum(count > 1 for count in ids.values()),
            "proposal_instances_with_reused_ids": sum(count for count in ids.values() if count > 1),
            "run19_source": str(RUN_DIR.resolve()),
        },
        "episodes": episode_summary(proposals, resolutions),
        "resolutions": resolutions,
        "promotions": promotions,
        "carryovers": carryovers,
        "deletions": groups["deletions"],
        "proposals": proposals,
    }
    options.json.parent.mkdir(parents=True, exist_ok=True)
    options.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    options.markdown.write_text(markdown(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(options.json.resolve())
    print(options.markdown.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
