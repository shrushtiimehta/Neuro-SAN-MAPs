# MAPs Park

A [Neuro SAN](https://github.com/cognizant-ai-lab/neuro-san) multi-agent network that plays the
**MAPs (Mini Amusement Parks)** benchmark. A team of LLM specialists manages one amusement park
over a 100-step episode, taking exactly one simulator action per step, trying to maximize
cumulative park value (target: **$1,000,000+**). Between episodes the agents *learn* — rolling
confirmed strategies into their playbooks so each run starts from the best run so far.

This repo (a [Neuro SAN Studio](https://github.com/cognizant-ai-lab/neuro-san-studio) fork) is the
agent side: the agent networks, the coded tools that wrap the simulator, an MCP server
([apps/maps_park/maps_mcp_server.py](apps/maps_park/maps_mcp_server.py)) that exposes the simulator
to the agents, and a loop runner that drives episode after episode. The park itself runs in one
**external** project you install separately:

- **MAPs** — the amusement-park simulator (a Node.js backend + a Python `map_py` interface),
  from Skyfall AI: <https://github.com/Skyfall-Research/MAPs>

If you have never touched MAPs or Neuro SAN Studio before, follow
[Setup from scratch](#setup-from-scratch) top to bottom — it covers both.

---

## How it works

Three agent networks (all in [registries/](registries/)) plus a Python loop runner:

| Network | File | Role |
|---|---|---|
| `player` | [player.hocon](registries/player.hocon) | **Game runner** — picks and validates one action per turn. |
| `watcher` | [watcher.hocon](registries/watcher.hocon) | **Mid-episode analyst** — health check at steps 10, 20 … 90. |
| `planner` | [planner.hocon](registries/planner.hocon) | **Start/end-of-episode analyst** — plans the episode, closes it out, learns. |

**Per turn** (`player`): `park_director` reads park status → `strategy_coordinator` fans out to
five domain specialists in parallel:

- `rides_manager`, `shops_manager`, `staffing_manager` — each proposes a typed action
- `park_layout_planner` — owns all `(x, y)` coordinate placement
- `research_lead` — proposes tech-tree research

Proposals go through `FinanceGate` (affordability), the coordinator picks one, and `ProposeAction`
validates it. The **runner** (not an agent) then dispatches the approved action once through
`ActionDispatcher`, straight to the typed `Maps*` MCP wrappers — no LLM hop for dispatch.
Pre-validation never touches the env, so a rejected proposal is re-prompted for free; a rejected
*dispatch* is logged as a `wait` and surfaced to the agent next turn.

**Learning between episodes.** The agents follow six **playbooks**
(`coded_tools/state/playbook_*.md`), seeded from
[coded_tools/config_files/](coded_tools/config_files/) on a fresh run.

- *Start of episode* — `planner` compares the best-ever episode against the last, writes
  the episode plan + coordinator strategy summary, demotes regression-linked rules, and logs fresh
  **trials** (hypotheses).
- *Mid-episode* (`watcher`) — emits a `VERDICT: on_track | underperforming | doomed`. A
  `doomed` verdict trips the runner's **early-abort guardrail**: past step 50 one strike aborts,
  before step 50 it takes two consecutive strikes. Aborting fast-forwards the rest of the episode
  with `wait()`s (the env has no early-reset), booking the loss cheaply.
- *End of episode* — `planner` runs the close-out: promote/resolve trials, roll confirmed
  hypotheses into the playbooks, and `advance_episode`.

Playbooks are snapshotted into `state/playbook_history/<ts>_<tag>/` at every episode boundary
(append-only, never deleted).

---

## Setup from scratch

### System requirements

- **Python 3.12** (MAPs requires 3.12; the studio supports 3.12/3.13 — use **3.12** so a single
  environment satisfies all three projects).
- **Node.js 22.15+** and npm (for the MAPs backend).
- **git**, and an **LLM provider API key** (OpenAI by default; Anthropic/Azure/others also work).

### 1. Clone the two repos

Clone MAPs anywhere convenient. The default (`$HOME/MAPs`) is what the run scripts expect; override
with an env var if you put it elsewhere (see step 6).

```bash
# this repo (the agent side) — you likely already have it
git clone https://github.com/cognizant-ai-lab/neuro-san-studio
cd neuro-san-studio                      # <- run everything below from here unless noted

# the simulator
git clone https://github.com/Skyfall-Research/MAPs ~/MAPs
```

### 2. Create ONE Python environment for everything

`run_all.sh` launches the MCP server and the studio with whichever `python` is on your PATH, so a
**single active virtual environment** must contain the deps for both projects.

```bash
python3.12 -m venv venv
source venv/bin/activate      # Windows: .\venv\Scripts\activate.bat
```

Keep this venv activated for every step below and every time you run the app.

### 3. Install the MAPs simulator

```bash
cd ~/MAPs
npm install                   # Node backend deps
pip install -e .              # installs the Python map_py interface into your venv
cd -                          # back to neuro-san-studio
```

### 4. MCP server dependencies

The MCP server ([apps/maps_park/maps_mcp_server.py](apps/maps_park/maps_mcp_server.py)) is vendored
into this repo and imports only `mcp`, `pydantic`, and `requests` (plus MAPs' `map_py` from step 3)
— all pulled in by the studio requirements in the next step. Nothing extra to install.

### 5. Install the studio and set your LLM key

From the `neuro-san-studio` root:

```bash
pip install -r requirements.txt
```

Set your provider key (OpenAI is the default). On macOS/Linux:

```bash
export OPENAI_API_KEY="sk-..."
```

To persist it and configure other providers (Anthropic, Azure, Ollama, …), copy `.env.example` to
`.env` and fill it in — the runner loads `.env` automatically.

### 6. (Optional) Point the run scripts at your MAPs clone

Only needed if you did **not** clone MAPs to the default location:

```bash
export MAPS_REPO=/path/to/MAPs
```

You're ready to run.

---

## Running

From the `neuro-san-studio` root, with the venv activated:

```bash
# Fresh run — resets playbooks to their config seeds, archives prior logs.
apps/maps_park/run_all.sh

# Resume an in-flight episode — keeps learned playbook edits and the current episode log.
apps/maps_park/run_all.sh --resume
```

`run_all.sh` boots all four processes and tears them all down on Ctrl-C:

1. **MAPs Node backend** — `node map_backend/server.js` (in `$MAPS_REPO`)
2. **MCP env** — the vendored `apps/maps_park/maps_mcp_server.py`, layout `the_islands`, difficulty
   `medium`, one park, on MCP port 8765
3. **Studio server** — `python -m neuro_san_studio run`, which registers the three agent networks
4. **Runner** — `python -m apps.maps_park.runner` (foreground; drives the episode loop)

Logs stream to `logs/maps_park/`. Any extra flags you pass are forwarded to the runner.

### Closing out a cancelled episode

If you Ctrl-C mid-episode, the services die before the end-of-episode close-out runs. Reboot the
backend in resume mode and fire the macro close-out once:

```bash
apps/maps_park/run_macro.sh
```

This is **not** read-only — it promotes/resolves trials and advances the episode, the same side
effects a normal episode end has.

### Runner flags

Run the loop directly with `python -m apps.maps_park.runner --help`. Notable options:

- `--resume` — keep learned `playbook_*.md` (default resets them to the config seed).
- `--consult-only {macro,micro}` — no game loop; invoke one analyzer against the latest episode log
  and exit (`run_macro.sh` uses this).
- `--micro-every N` — micro-analyst cadence (default 10 → steps 10, 20 … 90).
- `--reward-floor` / `--reward-goal` — thresholds the micro analyst judges `doomed` against.
- `--max-retries`, `--tick`, `--host`, `--port`.

### Troubleshooting

- **"MAPs repo not found"** — the run script can't find MAPs at its default path; set `MAPS_REPO`
  (step 6).
- **`ModuleNotFoundError: map_py`** — you skipped `pip install -e .` in `~/MAPs`, or you're not in
  the venv where you installed it.
- **Networks never register / port already in use** — a previous run left processes alive.
  `run_all.sh` tries to `pkill` them on startup; if the studio still won't come up, check
  `logs/maps_park/studio.log`. Ports used: MAPs backend 3000, MCP 8765, studio 8090.
- **Node errors on `npm install`** — check `node --version` is 22.15+.

---

## Layout

```
apps/maps_park/
  runner.py            loop runner — drives episodes, early-abort guardrail, playbook snapshots
  maps_mcp_server.py   vendored MCP server exposing the MAPs simulator to the agents
  run_all.sh           boot everything (MAPs backend + MCP env + studio + runner)
  run_macro.sh         one-shot macro close-out for a cancelled episode

coded_tools/             (flat — all tool modules directly here, no per-app subfolders)
  action_dispatcher.py         routes a validated action to the Maps* MCP wrappers
  maps_*.py                    typed action wrappers (place, move, modify, remove, wait, ...)
  propose_action.py            validate + persist the game-runner's proposal
  finance_gate.py              affordability gate
  park_status.py, *_telemetry  observation, status, and run/episode telemetry
  seed_playbooks.py            lay down state/playbook_*.md from config_files/
  {log,resolve,promote}_trial  the hypothesis (trial) ledger
  write_episode_plan.py, advance_episode.py, plot_rewards.py
  file_io.py, state_read.py, name_map.py   shared file helpers
  config_files/                seed playbooks + economics constants (tracked)
  state/                       live playbooks, ledgers, snapshots — runtime, gitignored, reseeded each run

registries/              player.hocon, watcher.hocon, planner.hocon — the three agent networks
logs/maps_park/          run.ep<NNN>.jsonl (one per episode), turns.jsonl, per-process logs
```

Outputs to watch after a run: per-episode reward trajectories in `logs/maps_park/run.ep<NNN>.jsonl`,
the per-turn ledger in `turns.jsonl`, and the evolving strategy in
`coded_tools/state/playbook_*.md`.
