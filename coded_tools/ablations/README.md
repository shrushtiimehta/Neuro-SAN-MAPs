# MAPs ablation tools

Only code or fixed inputs unique to an ablation belongs here. Runtime tools
used by the baseline and multiple arms remain directly under `coded_tools/`.

- `shared/` — experiment lifecycle helpers used by more than one arm.
- `single_agent/` — the merged economics and playbook inputs for that arm.
- `unstructured_player_planner_watcher/` — its free-form learning journal and
  plan writer.
- `g_memory_player_planner_watcher/` — three-layer G-Memory persistence and
  canonical-tool adapters; no learned rule or outcome is saved to Markdown.
