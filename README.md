# MAPs Park

This repository contains the Neuro SAN agent system for the **MAPs (Mini Amusement Parks)**
benchmark. The system manages one amusement park for 100 steps, takes exactly one simulator action
per step, and learns across episodes while targeting a cumulative park value of **$5,000,000+**.

The park simulator is a separate project:

- **MAPs simulator:** <https://github.com/Skyfall-Research/MAPs>
- **This repository:** agent networks, deterministic coded tools, the vendored MCP bridge, episode
  runner, persistent strategy state, telemetry, and ablation launchers

The canonical baseline is a three-network system:

| Network | Registry | Responsibility |
|---|---|---|
| `player` | [registries/player.hocon](registries/player.hocon) | Chooses and validates one action every turn. |
| `watcher` | [registries/watcher.hocon](registries/watcher.hocon) | Reviews the current episode every 10 successful steps and issues next-turn guidance. |
| `planner` | [registries/planner.hocon](registries/planner.hocon) | Plans before an episode, judges trials after it, and commits close-out. |

The Python runner owns environment stepping and lifecycle correctness. Agents propose decisions;
they do not dispatch actions directly to the simulator.

---

## Canonical baseline architecture

The registered baseline networks are declared in
[registries/manifest.hocon](registries/manifest.hocon). The recommended launcher is
[apps/maps_park/run_baseline_services.sh](apps/maps_park/run_baseline_services.sh).

### Player: one decision per turn

The `player` network contains a `strategy_coordinator` and six specialists:

| Agent | Reads | Produces |
|---|---|---|
| `strategy_coordinator` | Complete live status, complete economics, coordinator playbook, all active trials, one-turn scratchpad | Selects exactly one approved action. |
| `rides_manager` | Ride status, economics, playbook, and ride trials | At most one ride proposal. |
| `shops_manager` | Shop status, economics, playbook, and shop trials | At most one shop proposal. |
| `staffing_manager` | Staff status, economics, playbook, and staff trials | At most one staffing proposal. |
| `research_manager` | Research status, research and full economics, playbook, and research trials | At most one research proposal. |
| `guest_analyst` | Survey/guest status, playbook, and survey trials | A survey or guest-bottleneck proposal when needed. |
| `park_layout_planner` | Layout status, playbook, and layout trials | Coordinates for a selected place, move, or remove action. |

The normal turn flow is:

1. The runner refreshes `status_full.json` and all six specialist status projections.
2. The coordinator reads the current complete strategy, live status, economics, active trials, and
   its previous-turn scratchpad note.
3. It normally asks rides, shops, staffing, and research for proposals. Guest analysis is
   conditional. Layout is consulted only after an action requiring coordinates is selected.
4. `FinanceGate` checks affordability and runway and enriches approved proposals.
5. `ProposeAction` validates one final action and writes the proposal envelope.
6. The runner reads that envelope and calls `ActionDispatcher` exactly once.
7. The runner records the actual post-step result. A simulator-rejected action becomes a logged
   `wait` and its rejection is returned as feedback on the next turn.

Proposal validation never steps the environment. If no valid proposal is produced within the
configured retry limit, the runner advances the day with `wait` rather than hanging the episode.

### Watcher: current-episode correction

The runner invokes `watcher.mid_episode_analyst` after steps 10, 20, ..., 90 by default. It:

- calls `EpisodeTelemetry()` with no required episode argument, so the tool selects the latest/current
  episode and returns every committed step so far;
- reads the complete live `status_full`, not a coordinator projection;
- compares the current trajectory with the best completed episode;
- calls `ActiveTrials()` once, then reuses that result when reviewing micro trials;
- deletes micro trials that are failed, obsolete, or unproductive;
- logs as many new evidence-backed micro trials as the current state justifies; and
- returns a concise advisory that the runner injects into the player's next turn.

The watcher does not close the episode or promote learned rules. Its scratchpad is private to the
watcher and carries one note to its next check-in.

### Planner: start and end of every episode

The `planner` network routes through `macro_orchestrator` to one of two agents.

At `episode_start`, the planner:

1. reads the best and last completed episodes from telemetry;
2. reads the full champion park from `status_champion`;
3. reads `economics_all`, the game rules, the trial-outcome ledger, the coordinator playbook, and
   all six domain playbooks;
4. retires or refines carried-over trials and logs new macro trials;
5. writes an ordered, gap-free plan covering turns 1 through 100 using as many phases as needed;
6. writes the complete coordinator strategy and all six complete domain strategies; and
7. optionally leaves one scratchpad note for the episode close-out.

Before this planning pass, the runner reapplies the best champion plan when one exists. The planner
therefore refines the proven plan rather than accidentally inheriting a weaker last episode.

At `episode_end`, the planner:

1. reads the complete current episode through `EpisodeTelemetry()` and `status_full`;
2. evaluates every active trial as `confirmed`, `falsified`, `not_applied`, or `inconclusive`;
3. promotes confirmed rules into the correct domain playbook;
4. resolves the complete trial set; and
5. calls `advance_episode` last, which writes the durable close-out receipt.

Close-out is transactional. The runner does not advance without a receipt matching the episode and
reward, and it retries an unfinished close-out up to `--closeout-retries` times. Promotions and trial
resolution are implemented to tolerate a close-out retry without duplicating committed work.

### Runner: deterministic lifecycle and dispatch

[apps/maps_park/runner.py](apps/maps_park/runner.py) owns the operations that must not depend on LLM
behavior:

- seeding/restoring playbooks;
- refreshing status files before each decision;
- invoking planner and watcher at the correct boundaries;
- validating that a fresh proposal was written;
- dispatching one action to MAPs;
- writing authoritative local telemetry;
- enforcing close-out receipts;
- promoting a new champion only when it clears the reward floor and beats the current champion; and
- snapshotting champion playbooks.

The baseline launcher wraps this loop with
[apps/maps_park/bounded_runner.py](apps/maps_park/bounded_runner.py), which defaults to exactly 10
completed episodes. Set `MAPS_EPISODE_LIMIT=unlimited` for an unbounded run.

### HOCON tool wiring

The baseline exposes only the tools each network needs:

| Agent | Directly wired tools |
|---|---|
| `strategy_coordinator` | Six specialists, `FinanceGate`, `ProposeAction`, `state_read`, `scratchpad`, `ActiveTrials` |
| Every player specialist | `state_read`, `ActiveTrials` |
| `watcher.mid_episode_analyst` | `state_read`, `EpisodeTelemetry`, `RunTelemetry`, `ActiveTrials`, `LogTrial`, `DeleteTrial`, `scratchpad` |
| `planner.episode_start` | `RunTelemetry`, `state_read`, `CarryoverTrials`, `LogTrial`, `WriteEpisodePlan`, `scratchpad` |
| `planner.episode_end` | `state_read`, `EpisodeTelemetry`, `ActiveTrials`, `PromoteTrial`, `ResolveTrials`, `advance_episode`, `scratchpad` |

The baseline logical file reads are equally explicit:

- the coordinator uses `playbook_coordinator`, `status_full`, and `economics_all`;
- rides, shops, and staff use their matching playbook, live status, and economics files;
- research uses `playbook_research`, `status_research`, `economics_research`, and `economics_all`;
- layout and survey use their matching playbook and live status files;
- watcher file aliases are only `status_full` and `trial_strategies_outcome`; and
- planner file aliases are `economics_all`, `maps_game_docs`, `episode_checklist`, the coordinator
  and six domain playbooks, `status_full`, `status_champion`, and `trial_strategies_outcome`.

The root manifest registers all three canonical networks. The launcher waits until `player`,
`watcher`, and `planner` all appear in Studio's registry response before starting the runner.

---

## Persistent context and state contracts

Agent conversation history is deliberately short and is not the durable memory layer. Restarts do
not guarantee that an agent's previous chat messages remain available. Durable continuity comes from
the files and telemetry below; the three scratchpads are private, one-use hand-offs rather than chat
archives.

### Live and champion status

`status_full` and `status_champion` have the same complete cross-domain shape, but they represent
different moments:

| Logical name | File | Meaning | Baseline readers |
|---|---|---|---|
| `status_full` | `state/status_full.json` | The latest live park snapshot, refreshed before every player turn and left at the finished park after step 100. | Coordinator, watcher, planner close-out. |
| `status_champion` | `state/status_champion.json` | A frozen copy of the full finished park from the best promoted episode. | Planner episode start. |

The baseline intentionally has no separate `status_coordinator.json` and no
`status_layout_champion.json`. Those filtered champion aliases are not part of the canonical baseline.
The player specialists still receive focused live projections (`status_rides`, `status_shops`,
`status_staff`, `status_research`, `status_layout`, and `status_survey`) to keep each specialist's
turn context relevant. The coordinator and watcher receive the unfiltered full status.

The canonical baseline also does not create or consume `last_reward.md`. Reward comes from full
status and authoritative telemetry. `MAPS_USE_LAST_REWARD=0` is set by the baseline launcher, and a
stale legacy file is removed at startup. Other experimental arms retain their own defaults unless
their launcher opts out.

### Playbooks and episode strategies

The baseline has seven working playbooks:

```text
playbook_coordinator.md
playbook_rides.md
playbook_shops.md
playbook_staff.md
playbook_research.md
playbook_layout.md
playbook_survey.md
```

Every domain playbook is read as one complete document:

1. the planner-written strategy for the current episode is at the top;
2. the hand-authored domain instructions follow; and
3. confirmed learned rules promoted from prior trials remain in the learned-rules section.

The coordinator playbook similarly carries the complete cross-domain executable strategy at its top.
The strategy blocks are replaced as a unit each episode; the core instructions and promoted learned
rules are preserved. Player and watcher `state_read` calls allow up to 120,000 characters, while
`status_full` and `status_champion` are protected from the generic cap for every network. The current
planner HOCON does not set an explicit override for its non-status reads, so its playbooks, game docs,
economics, checklist, and outcome ledger use `StateRead`'s 20,000-character default. This is a read
limit only; it does not truncate the files on disk.

`WriteEpisodePlan` validates its complete payload before changing any file. It rejects:

- missing or non-list checklist data;
- missing, null, empty, or placeholder coordinator strategies;
- a missing domain;
- null, empty, or placeholder domain strategies; and
- unknown domain keys.

The required domains are `rides`, `shops`, `staff`, `research`, `layout`, and `survey`. If validation
fails, the planner may correct the named fields and retry only the full `WriteEpisodePlan` call up to
twice. This prevents a value such as `None`, `null`, or `keep unchanged` from replacing a valid domain
strategy while still allowing a recoverable schema mistake to be fixed.

### Why the seed files exist

The seed files in [coded_tools/config_files/](coded_tools/config_files/) are not exposed as
`state_read` aliases because agents should read the working `state/playbook_*.md` files. The
deterministic `SeedPlaybooks` tool copies the seeds into the working state when a playbook is missing
or when `--fresh` requests a reset.

Confirmed baseline rules are mirrored into both the working domain playbook and its corresponding
seed, tagged `(learned epN)`, so normal future runs retain them. `--fresh` archives the old state and
removes promoted-rule lines from the baseline seeds before reseeding; the hand-authored instructions
remain intact. The Solo merged seed is a frozen experiment input and is not modified by promotion.

### Episode checklist

`state/episode_checklist.md` is active runtime state, not an unused prompt artifact:

- the planner writes the complete turn-phased execution plan at episode start, including each
  phase's move order, targets, transition condition, and phase-specific contingency;
- the planner can read it when revising the champion plan; and
- `EpisodePhaseMiddleware` converts the completed simulator step into the action turn being planned,
  selects its exact phase and the immediately following phase, and injects the completed step, action
  turn, current phase, and next phase into every model call made by the coordinator and all six player
  specialists.

The checklist is the sole owner of turn ranges and phase timing. The coordinator and domain
playbook strategy blocks instead hold the complete phase-independent policies, numeric triggers,
dependencies, and contingencies, so the same schedule is not duplicated across seven playbooks.
The phase is execution context, not park state: it is absent from `status_full` and every specialist
status projection. Each player agent receives only the relevant phase line through middleware,
without receiving the entire checklist.

### Trial ledgers

| File | Purpose |
|---|---|
| `trial_strategies.md` | Active rule text keyed by trial ID. |
| `trial_strategies_criteria.md` | Trial origin, domain, activation, rationale, and success/failure criteria. |
| `trial_strategies_outcome.md` | Append-only verdict history for completed macro trials. |

Macro trials are created at episode start and judged at close-out. Micro trials are created and
pruned by the watcher during the current episode. `ActiveTrials` joins the active rule and criteria
files so readers receive a complete trial record.

### Champion promotion

An episode becomes champion only when its cumulative reward:

1. meets `--reward-floor` (default `350000`); and
2. strictly exceeds the existing champion reward.

Promotion saves:

- `plan_current.json` as `plan_last_good.json`;
- the new value in `champion_reward.json`;
- the finished complete status as `status_champion.json`; and
- all current playbooks under `state/playbook_history/<timestamp>_epNNN_champion/`, with a
  `summary.json` containing final metrics.

Only champion episodes receive champion snapshots. Losing episode boundaries are not added to the
champion ladder.

---

## Setup from scratch

### Requirements

- Python **3.12**
- Node.js **22.15+** and npm
- Git
- An LLM provider key; the checked-in baseline configuration uses OpenAI models
- A W&B account only if W&B mirroring is enabled

### 1. Clone both repositories

```bash
git clone <this-repository-url> neuro-san-studio
cd neuro-san-studio

git clone https://github.com/Skyfall-Research/MAPs "$HOME/MAPs"
```

The launchers look for MAPs at `$HOME/MAPs` by default. Set `MAPS_REPO` if it lives elsewhere:

```bash
export MAPS_REPO=/absolute/path/to/MAPs
```

### 2. Create one Python environment

Use one environment for Studio, the MCP server, and MAPs' Python package:

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### 3. Install MAPs

```bash
cd "$HOME/MAPs"
npm install
pip install -e .
cd /path/to/neuro-san-studio
```

### 4. Install this repository

```bash
pip install -r requirements.txt
```

The vendored MCP server imports MAPs' `map_py` package from the editable installation above; no
third simulator repository is required.

### 5. Configure the model provider

For OpenAI:

```bash
export OPENAI_API_KEY="sk-..."
```

Alternatively, create a repository-root `.env` and configure a supported provider there. Studio and
the runner load `.env` automatically.

### 6. Configure telemetry

W&B is the default mirror:

```bash
wandb login
export WANDB_PROJECT=maps-park-ablations
```

To keep only local JSONL/TSV telemetry:

```bash
export MAPS_TELEMETRY_BACKEND=jsonl
```

Local telemetry remains the operational source of truth even when W&B is enabled.

---

## Run the canonical baseline

From the repository root:

```bash
apps/maps_park/run_baseline_services.sh
```

This is the preferred baseline launcher. It uses:

- networks: `player / watcher / planner`;
- state: `state/`;
- seeds: `coded_tools/config_files/`;
- logs: `logs/maps_park/`;
- ports: Node `3000`, MCP `8765`, Studio `8090`;
- W&B group: `baseline`;
- OpenAI output format: `responses/v1`; and
- a default limit of 10 completed episodes.

It starts each service in its own process group, refuses to take an occupied port, and tears down
only the processes it started. The baseline intentionally skips the cross-arm canonical-copy
validator; this does not disable runtime proposal, plan, close-out, or state validation.

### Run modes

| Command | Behavior |
|---|---|
| `apps/maps_park/run_baseline_services.sh` | Starts a new simulator run from the newest champion playbooks and plan, or seeds if no champion exists. Prior active logs are archived. |
| `apps/maps_park/run_baseline_services.sh --resume` | Continues the in-flight simulator episode and retains its state and logs. It skips the episode-start planner only when the episode is genuinely mid-flight. |
| `apps/maps_park/run_baseline_services.sh --fresh` | Archives the working state to a dated `_prewipe` directory, strips promoted rules from baseline seeds, and starts without loading any prior champion. |

`--fresh` is recoverable: prior state is moved under `state/playbook_history/`; it is not destroyed.
The simulator-owned `park_state.pkl` and the history directory itself remain in place.

Control the episode count with an environment variable:

```bash
MAPS_EPISODE_LIMIT=3 apps/maps_park/run_baseline_services.sh --fresh
MAPS_EPISODE_LIMIT=unlimited apps/maps_park/run_baseline_services.sh
```

Archived prior-run telemetry is excluded from best/last comparisons by default. Opt in explicitly:

```bash
apps/maps_park/run_baseline_services.sh --include-archived
```

### Processes started

1. MAPs Node backend: `node map_backend/server.js --vis`
2. Vendored MCP server: `apps/maps_park/maps_mcp_server.py`, using `the_islands`, `medium`, one park
3. Neuro SAN Studio HTTP server in `--server-only` mode
4. Bounded Python runner in the foreground

Press Ctrl-C to stop the runner and its service stack.

### Useful runner flags

Arguments not consumed by the launcher are forwarded to the runner:

```text
--tick SECONDS             delay between turns; 0 disables it
--max-retries N            proposal-validation attempts before a wait
--closeout-retries N       corrected close-out retries; default 2
--micro-every N            watcher cadence; default 10
--reward-floor N           minimum champion reward; default 350000
--reward-goal N            target supplied to analysis; default 5000000
--include-archived         allow telemetry tools to inspect archived prior runs
--no-archived              exclude archived prior runs; the default
```

Run `python -m apps.maps_park.runner --help` for the underlying loop's complete CLI.

### Legacy launcher

[apps/maps_park/run_all.sh](apps/maps_park/run_all.sh) remains available for manual and Solo
compatibility. Unlike the isolated baseline launcher, it uses fixed default ports, launches the full
Studio process, and kills matching leftover MAPs/Studio processes before startup. Use
`run_baseline_services.sh` for the canonical baseline, especially when other experiment stacks may
be running.

---

## Solo and ablation runs

The dedicated eight-arm model/topology/self-improvement experiment is documented
in [docs/maps_ablation_study.md](docs/maps_ablation_study.md). It includes the
Qwen single/multi comparisons, no-carryover ten-episode controls, GPT-5 Mini
single/multi runs, strict W&B telemetry, and generation of isolated repository
replicas. It also provides one portable Qwen bundle containing both Studio and
the MAPS simulator for execution on an M4 Max.

### Solo

The Solo arm uses one player agent and one planner agent. The planner also performs periodic watcher
analysis:

```bash
apps/maps_park/run_single_agent_ablation.sh --fresh
apps/maps_park/run_single_agent_ablation.sh --resume
```

Its state is isolated under `state_solo/`, logs under `logs/maps_park_solo/`, and default ports are
Node `3050`, MCP `8815`, and Studio `8140`.

Solo intentionally differs from the structured baseline:

- `player_solo` receives one full status and one merged playbook;
- `planner_solo` reads and writes one complete all-domain strategy;
- one frozen merged seed, `seed_playbook_all.md`, contains all role instructions; and
- one frozen `economics_merged.md` contains its economics context.

The canonical baseline now has equivalent complete economics and full coordinator/watcher status,
while retaining its specialist topology and per-domain executable strategies.

`apps/maps_park/run_solo.sh` is the legacy Solo wrapper around `run_all.sh`; the isolated ablation
launcher above is preferred for bounded experiments.

### Eight-arm batch

The primary ablation launchers are:

| Launcher | Player | Periodic analyst | Episode planner/closer |
|---|---|---|---|
| `run_player_with_watcher.sh` | Multi-agent player | Watcher | Off |
| `run_player_with_planner.sh` | Multi-agent player | Off | Planner |
| `run_embedded_player_planner_watcher.sh` | Embedded combined network | Same combined network | Same combined network |
| `run_unstructured_player_planner_watcher.sh` | Multi-agent player | Watcher | Unstructured-learning planner |
| `run_g_memory_player_planner_watcher.sh` | Multi-agent player + G-Memory recall | Watcher | Canonical planner |
| `run_single_agent_ablation.sh` | Solo player | Solo planner | Solo planner |
| `run_multi_player_single_planner.sh` | Multi-agent player | Single planner | Single planner |
| `run_single_player_multi_planner_watcher.sh` | Single player | Canonical watcher | Canonical planner |

Run all eight sequentially for 10 completed episodes each:

```bash
apps/maps_park/run_all_ablation_arms.sh
```

The batch uses `--fresh`, forwards additional runner flags to every arm, and finishes after 80 total
episodes. Each arm owns a separate state directory, log directory, manifest, seed mirror, W&B group,
and default port triplet.

The GMemory arm keeps the same planning, periodic watching, player topology, prompts, and 100-turn episode.
It uses the actual [GMemory implementation](https://github.com/bingreeky/GMemory) at pinned commit
`7b581c51d993bd600df14691d101d7e601040cc6` for completed episode trajectories and recall.
The runner captures planner, watcher, coordinator, and specialist requests, replies, and delegations from
Neuro SAN's message stream. Their parent and target links become GMemory interaction-graph edges, and a
bounded coordination summary is included in episode retrieval.
The current checklist, domain strategies, active trials, verdicts, scratchpads, and champion plan live in
`g_memory_live.sqlite3` because upstream GMemory accepts completed tasks rather than mutable in-flight
records. No runtime playbook, checklist, trial ledger, or scratchpad Markdown files are created in this arm.
Immutable seed guidance is read once into the live store, with other arms' learned lines removed.

Prepare this optional arm with `apps/maps_park/setup_g_memory.sh`, then run
`apps/maps_park/run_g_memory_player_planner_watcher.sh`. Set `MAPS_GMEMORY_MODEL` for the model used by
GMemory's extraction and reranking use the arm's `gpt-5.5` model by default. Setup downloads the
upstream embedding model. The checkout stays outside this repository because the upstream repository does
not include a license file.

Additional controlled launchers cover full-status subagents, GPT-5 Mini, and
single-agent-instructions experiments. Some are designed for isolated replicas and require ports
from `.ablation-instance.env`; launch those through:

```bash
apps/maps_park/run_replica_ablation.sh --fresh
```

The shared isolated service implementation is
[apps/maps_park/run_ablation_services.sh](apps/maps_park/run_ablation_services.sh). Non-baseline arms
run [apps/maps_park/validate_ablations.py](apps/maps_park/validate_ablations.py) before starting unless
their launcher explicitly changes that policy.

Control-side player, watcher, and planner HOCONs are generated from the canonical registries by
`scripts/sync_baseline_ablation_prompts.py`. Their instruction strings are required to match the
baseline verbatim; only experiment infrastructure such as model selection may differ. A treatment
side—such as the merged Solo agent, single planner, single player, unstructured planner, full-status
subagents, or embedded self-critic—keeps the instructions that define that treatment. Run the sync
script with `--check` to detect control-prompt drift without rewriting files.

### Champion replay

[apps/maps_park/run_replay.sh](apps/maps_park/run_replay.sh) plays with the planner off. When an
optional `state_1.8M/restore.sh` snapshot is present, the default mode restores it first:

```bash
apps/maps_park/run_replay.sh
apps/maps_park/run_replay.sh --keep-state
```

The default command requires and calls `state_1.8M/restore.sh`; `--keep-state` uses the current
`state/` contents and does not require that snapshot directory.

### One-shot close-out

If a legacy `run_all.sh` run was interrupted after an episode boundary but before close-out, use:

```bash
apps/maps_park/run_macro.sh
```

This is not read-only. It resumes the environment, evaluates and promotes/resolves trials, calls
`advance_episode`, and may change playbooks. The isolated baseline runner normally performs and
retries this close-out automatically.

---

## Runtime files and telemetry

### Baseline state directory

A mature `state/` directory may contain:

| File or directory | Owner and purpose |
|---|---|
| `park_state.pkl` | Simulator persistence used by MCP resume. |
| `latest_observations.json` | Latest observation cache used to build turn status. |
| `status_full.json` | Complete current park snapshot. |
| `status_<domain>.json` | Focused live status for each player specialist. |
| `status_champion.json` | Complete final park of the promoted champion. |
| `playbook_coordinator.md` | Current full coordinator strategy, base instructions, learned rules. |
| `playbook_<domain>.md` | Current complete domain strategy, base instructions, learned rules. |
| `episode_checklist.md` | Ordered turn phases for the current episode. |
| `plan_current.json` | Exact latest planner payload. |
| `plan_last_good.json` | Exact strategy payload of the current champion. |
| `champion_reward.json` | Reward attached to `plan_last_good`. |
| `trial_strategies*.md` | Active trials, criteria, and append-only outcomes. |
| `closeout_pending.json` | In-progress close-out transaction marker. |
| `closeout_receipt.json` | Durable completed close-out commit marker. |
| `.wandb_run_path` | Pointer used to reconnect W&B on resume. |
| `playbook_history/` | Champion snapshots and recoverable pre-wipe archives. |

Not every file exists before its first relevant event.

### Local logs

The baseline writes under `logs/maps_park/`:

| Output | Contents |
|---|---|
| `run.epNNN.jsonl` | Authoritative committed post-step rows for one episode. |
| `turns.jsonl` | Per-turn attempts, proposals, verified results, and token counts. |
| `episode_cost.jsonl` | Per-episode LLM calls, tokens, estimated cost, and final reward. |
| trajectory TSV files | Simulator trajectory output. |
| `park_ids.jsonl` | Permanent cumulative park-ID ledger; not moved with normal log archives. |
| `maps_node.log` | Node backend process output. |
| `maps_mcp.log` | MCP server process output. |
| `studio.log` | Studio registration and model/tool output. |
| `prior-runs/<timestamp>/` | Archived active logs from earlier non-resume runs. |

`EpisodeTelemetry` always learns from the local per-episode JSONL files. W&B is a mirror, not the
runtime read path.

### W&B and Weave utilities

Fresh W&B runs automatically choose the next run number for their arm. Set `MAPS_RUN_NUMBER` only
when an explicit number is required. The transient W&B cache is kept under `/tmp/maps-wandb`.

Import multi-episode legacy run history:

```bash
python scripts/import_all_ablation_history_to_wandb.py
```

Use `--dry-run` to inventory without uploading. Backfill episode-root/turn-child trace trees with:

```bash
python scripts/backfill_ablation_traces_to_weave.py
```

---

## Repository layout

```text
apps/maps_park/
  runner.py                         canonical lifecycle and game loop
  bounded_runner.py                 optional completed-episode limit
  ablation_runner.py                bounded experimental lifecycle adapter
  solo_runner.py                    Solo path/session adapter
  maps_mcp_server.py                vendored MAPs-to-MCP bridge
  run_baseline_services.sh          recommended canonical baseline launcher
  run_ablation_services.sh          shared isolated experiment service stack
  run_all_ablation_arms.sh          sequential eight-arm batch
  run_all.sh                        legacy general launcher
  run_replay.sh                     checked-in champion replay
  run_macro.sh                      legacy one-shot planner close-out

registries/
  manifest.hocon                    canonical registered networks
  player.hocon                      multi-agent player
  watcher.hocon                     current-episode watcher
  planner.hocon                     episode planner and closer
  ablations/                        isolated experimental manifests/HOCONs

coded_tools/
  action_dispatcher.py              dispatches one validated proposal
  propose_action.py                 validates and persists one proposal
  finance_gate.py                   affordability/runway gate
  park_status.py                    full and specialist status writer
  episode_telemetry.py              current/latest episode evidence
  run_telemetry.py                  best/last and cross-run evidence
  seed_playbooks.py                 deterministic seed-to-working-state copy
  write_episode_plan.py             complete validated strategy writer
  champion_plan.py                  champion plan promotion/restoration
  advance_episode.py                durable close-out commit
  active_trials.py                  joined active trial reader
  log_trial.py                      trial creation
  promote_trial.py                  confirmed-rule promotion
  resolve_trials.py                 complete trial verdict commit
  state_read.py                     allow-listed logical state reader
  scratchpad.py                     private one-use network notes
  config_files/                     baseline economics, game docs, and seven seeds
  ablations/                        experiment-specific coded tools and frozen inputs

state/                              canonical live state; runtime-generated
state_solo/                         isolated Solo live state
state_ablations/                    isolated per-arm state
state_1.8M/                         optional 1,861,276-reward replay snapshot
ablation_seeds/                     private per-arm seed mirrors
logs/                               local process and experiment telemetry
tests/                              unit and integration coverage
```

---

## Troubleshooting

### MAPs repository not found

Set the simulator path explicitly:

```bash
export MAPS_REPO=/absolute/path/to/MAPs
```

### `ModuleNotFoundError: map_py`

Activate the same venv used by this repository and reinstall MAPs:

```bash
source venv/bin/activate
pip install -e /absolute/path/to/MAPs
```

### Port already in use

The isolated launcher will not kill an unrelated process. Stop the prior stack or override all three
ports with unique values:

```bash
MAPS_NODE_PORT=3100 \
MAPS_MCP_PORT=8865 \
MAPS_STUDIO_PORT=8190 \
apps/maps_park/run_baseline_services.sh
```

If ports are changed, the launcher derives the MCP URL and passes the Studio port to the runner.

### Studio does not register all networks

Inspect `logs/maps_park/studio.log`. The baseline must register `player`, `watcher`, and `planner`
before the runner starts.

### Resume behavior is surprising

- Use `--resume` only for the same in-flight simulator/state/log tree.
- Use no mode flag to start a new run from the best champion.
- Use `--fresh` to archive state and deliberately ignore prior learning.

If a resumed episode already reached step 100 without a receipt, the runner retries close-out before
starting the next episode. If it is genuinely mid-episode, the start planner is skipped so the current
plan is not rewritten halfway through.

### A strategy field is rejected

`WriteEpisodePlan` reports the exact missing, null, placeholder, or unknown field. The planner should
retry the entire payload—checklist, coordinator strategy, and all six domain strategies—without
repeating earlier trial-logging side effects.

### Deprecation or Langfuse startup messages

Repository code uses Neuro SAN's supported public message type and initializes Langfuse without the
removed `leaf_common.config.resolver_util` helper. Do not modify the installed Neuro SAN package to
address these messages; inspect the local Studio log and repository integration first.
