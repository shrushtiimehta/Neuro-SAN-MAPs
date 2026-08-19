#!/usr/bin/env python3
"""One-command triage for a MAPs run: what is broken, and is the loop alive?

    python scripts/run_health.py

Four checks, in the order that catches the worst failures first:

  1. LIVENESS  — did each consultant tool actually run this episode? This is the
     one that matters. Both deadlocks found on 2026-08-12 were SILENT: the
     episode kept scoring, the runner printed nothing unusual, and the learning
     loop had been dead for four days. Only the tool timestamps showed it.
  2. INPUTS    — every state_read target in every network resolves to a real
     file. A missing one is how both deadlocks started.
  3. LEDGER    — duplicate trial ids (one shadows the other in the parser dict)
     and trials stranded from old episodes.
  4. ERRORS    — distinct agent-visible errors, ranked, digits normalised so the
     same failure with different numbers collapses to one line.

Read-only. Prints a report and exits non-zero if anything in 1-3 is wrong, so it
can sit in a cron/loop and only shout when it matters.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
THINKING = REPO / "logs/thinking_dir"
LOGS = REPO / "logs/maps_park"

# Tool -> the pass it belongs to. If a pass ran but one of its tools has a stale
# timestamp, that pass is aborting partway — exactly the deadlock signature.
LIVENESS = {
    "macro_orchestrator.episode_start.WriteEpisodePlan": "episode_start writes the plan",
    "macro_orchestrator.episode_end.ResolveTrials": "episode_end resolves trials",
    "macro_orchestrator.episode_end.advance_episode": "episode_end closes the episode",
    "strategy_coordinator.ProposeAction": "coordinator proposes actions",
}
STALE_HOURS = 6.0


def _age_hours(path: Path) -> float | None:
    return (time.time() - path.stat().st_mtime) / 3600 if path.exists() else None


def check_liveness() -> list[str]:
    print("== LIVENESS " + "=" * 56)
    problems = []
    for name, what in LIVENESS.items():
        age = _age_hours(THINKING / name)
        if age is None:
            print(f"  NEVER RAN  {what}")
            problems.append(f"{what}: never ran")
        elif age > STALE_HOURS:
            print(f"  STALE {age:6.1f}h  {what}")
            problems.append(f"{what}: last ran {age:.1f}h ago")
        else:
            print(f"  ok    {age:6.1f}h  {what}")
    return problems


def check_inputs() -> list[str]:
    print("\n== INPUTS " + "=" * 58)
    try:
        from pyhocon import ConfigFactory
    except ImportError:
        print("  (pyhocon not installed; skipped)")
        return []
    missing, total = set(), 0
    for net in ("player", "watcher", "planner"):
        cfg = ConfigFactory.parse_string((REPO / f"registries/{net}.hocon").read_text(),
                                         basedir=str(REPO))
        for tool in cfg["tools"]:
            args = tool.get("args", {})
            name_map = dict(args).get("name_map") if hasattr(args, "get") else None
            for key, rel in (dict(name_map).items() if name_map else []):
                total += 1
                if not (REPO / str(rel)).exists():
                    missing.add(f"{net}: {key} -> {rel}")
    print(f"  {total} state_read targets checked")
    for m in sorted(missing):
        print(f"  MISSING  {m}")
    return [f"missing state file: {m}" for m in sorted(missing)]


def check_ledger() -> list[str]:
    print("\n== LEDGER " + "=" * 58)
    problems = []
    strategies = REPO / "coded_tools/state/trial_strategies.md"
    if not strategies.exists():
        print("  no trial ledger yet")
        return problems
    ids = re.findall(r"^- (t\d+_\d+)", strategies.read_text(), re.M)
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    if dupes:
        print(f"  DUPLICATE IDS  {dupes}  (one shadows the other when parsed)")
        problems.append(f"duplicate trial ids: {dupes}")
    sys.path.insert(0, str(REPO))
    try:
        from coded_tools.active_trials import ActiveTrials
        res = ActiveTrials().invoke({}, {})
        print(f"  {res['count']} active, {len(res.get('withheld_stale', []))} withheld as stale")
        if res.get("withheld_stale"):
            print(f"  stranded from old episodes: {sorted(res['withheld_stale'])}")
            problems.append("stranded trials — a close-out is not resolving them")
    except Exception as exc:                       # noqa: BLE001 - triage must not crash
        print(f"  (could not read active trials: {exc})")
    return problems


def report_errors(top: int = 12) -> None:
    print("\n== ERRORS " + "=" * 58)
    if not THINKING.exists():
        print("  no thinking dir")
        return
    counts: Counter = Counter()
    for f in THINKING.iterdir():
        if not f.is_file():
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for m in re.findall(r"ERROR: [^\"'\\\n]{0,120}", text):
            m = re.sub(r"\d+", "N", m).strip()
            # The prompt's own error-handling boilerplate is not a failure.
            if "verbatim error text" in m:
                continue
            counts[m] += 1
    for msg, n in counts.most_common(top):
        print(f"  {n:>6}  {msg}")
    if not counts:
        print("  none")
    print("\n  NOTE: counts are inflated — a prompt is re-logged each turn it stays")
    print("  in context. Use them to rank causes, not to size impact.")


def report_retries() -> None:
    print("\n== RETRIES / COST " + "=" * 50)
    turns = LOGS / "turns.jsonl"
    if turns.exists():
        rows = [json.loads(l) for l in turns.read_text().splitlines() if l.strip()]
        # turns.jsonl spans every runner process ever; keep the current one.
        resets = [i for i in range(1, len(rows)) if rows[i]["turn"] <= rows[i - 1]["turn"]]
        rows = rows[max(resets or [0]):]
        att = Counter(r.get("attempts") for r in rows)
        wasted = sum((a - 1) * n for a, n in att.items() if a)
        print(f"  attempts per turn: {dict(sorted(att.items()))}")
        print(f"  wasted round trips: {wasted} of {len(rows)} turns")
    cost = LOGS / "episode_cost.jsonl"
    if cost.exists():
        for line in cost.read_text().splitlines()[-3:]:
            e = json.loads(line)
            print(f"  ep{e['episode']}: ${e['cost_usd']:.2f}  reward {e['final_reward']}  "
                  f"${e['cost_per_reward'] or 0:.6f}/reward")


def main() -> int:
    os.chdir(REPO)
    problems = check_liveness() + check_inputs() + check_ledger()
    report_errors()
    report_retries()
    print("\n" + "=" * 68)
    if problems:
        print(f"{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
