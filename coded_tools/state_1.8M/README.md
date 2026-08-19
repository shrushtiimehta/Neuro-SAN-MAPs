# state_1.8M — ep3's champion state (cumulative_reward 1,861,276)

Everything the **player** reads, exactly as ep3 read it. Copy it over
`coded_tools/state/` with `./coded_tools/state_1.8M/restore.sh` and replay
without the planner: the checklist, the playbooks and the trials are already
fixed, so a fresh 100-step run tests whether the same strategy earns the
same reward.

| file | why the player needs it |
|---|---|
| `episode_checklist.md` | ParkStatus derives `current_phase` from it every turn |
| `playbook_coordinator.md` | strategy_coordinator reads it every turn |
| `playbook_{rides,shops,staff,research,layout,survey}.md` | each specialist reads its own |
| `trial_strategies.md` + `_criteria.md` | `ActiveTrials()` — ep3's six trials, the priority for the episode |
| `trial_strategies_outcome.md` | the ledger as of ep3's start (no future knowledge) |
| `plan_last_good.json`, `champion_reward.json` | only read if you let the macro run: it restores this plan as the base |
| `summary.json` | ep3's verified final row, for reference |

Provenance / edits, so nothing here is a mystery:

- playbooks are `playbook_history/20260819-103820_ep003_champion/` **minus the 3
  lines tagged `(learned ep3)`** — ep3's own close-out promoted those; they did
  not exist while ep3 played. Add them back if you want to replay the champion
  *artifact* rather than ep3's inputs.
- trials `t3_1`–`t3_6` are recovered verbatim from the ep3 close-out
  `ActiveTrials` dump in `logs/thinking_dir/`. `t3_6` is the micro trial logged
  at step 90 — the red-drink swap that took park_value 1.04M → 1.75M in the last
  eight steps. `t3_1`–`t3_3` are `replace_line` trials whose `find_text` still
  points at the pre-ep3 playbook lines, which is correct for these files.
- `trial_strategies_outcome.md` is truncated after ep3's carryover lines.
- nothing live is included: `status_*.json`, `latest_observations.json` and
  `park_state.pkl` belong to the running park, and `restore.sh` deletes the
  first two so no ep7 leftovers are read on turn 1.

Do not run with `--fresh` — it archives this state straight back out again.

One catch worth knowing before you run: `ActiveTrials` withholds any trial older
than `current_episode - 1`, so these `ep=3` lines are only visible if the replay
starts a **fresh park at episode 0** (what `run_all.sh` does without `--resume`).
Verified: at ep0 all six parse, per-domain counts rides/shops/staff/research/layout
= 1/2/1/1/1. If you replay at episode 8 or later instead, renumber first:

    sed -i 's/ ep=3 / ep=<E> /' coded_tools/state/trial_strategies_criteria.md
