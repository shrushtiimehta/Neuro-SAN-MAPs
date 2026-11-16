# MAPs ablation registries

Each experiment arm has its own manifest and directory. This keeps the server
for one arm from loading networks belonging to another arm.

The `shared/` definitions are included by arms that intentionally use the same
player, planner, or watcher. Arm directories contain only thin includes plus
the networks unique to that arm, so shared prompts do not get copied and drift.

Hybrid topology arms:

- `multi_player_single_planner/` — canonical seven-agent player plus one planner
  agent that owns episode start, periodic watching, and episode close-out.
- `single_player_multi_planner_watcher/` — one all-domain player agent plus the
  canonical planner and watcher networks.

Shared-context topology arms:

- `full_status_subagents/` — baseline split playbooks and economics with one
  complete read-only park-status snapshot visible to every player agent.

Model-only arms:

- `baseline_gpt5_mini/` — canonical baseline player, watcher, and planner with
  every active LLM switched to `gpt-5-mini`.
- `single_agent_gpt5_mini/` — the two-agent solo topology with both active LLMs
  switched to `gpt-5-mini`.
- `qwen4b_multi/` and `qwen4b_single/` — uniform `qwen3:4b` topology controls.
- `qwen4b_strong_planner_multi/` and `qwen4b_strong_planner_single/` —
  `qwen3:4b` players with `qwen3:30b-a3b` planning and periodic analysis.

No-carryover arms:

- `no_self_improvement_multi/` and `no_self_improvement_single/` retain the
  episode-start planner and periodic watcher. Their runner skips planner
  close-out, restores immutable seeds, and clears every cross-episode learning
  channel before the next episode.

Memory-backend arms:

- `g_memory_player_planner_watcher/` keeps the canonical multi-agent player,
  planner, watcher, prompts, tools, and lifecycle. Its tool classes redirect
  cross-episode trajectories, trial outcomes, and learned insights into a
  three-layer G-Memory SQLite store and retrieve relevant memory dynamically.
