# MAPS model, topology, and self-improvement study

This study compares model size, agent topology, planner capacity, and
cross-episode self-improvement without changing the MAPS simulator, seed
playbooks, action budget, or episode length. Every arm completes exactly ten
100-step episodes and streams its steps, turns, episode costs, and final park
records to W&B.

## Experiment matrix

| Arm | Topology | Player | Planner/watcher | Self-improvement |
|---|---|---|---|---|
| `qwen4b_multi` | Multi-agent | `qwen3:4b` | `qwen3:4b` | On |
| `qwen4b_single` | Single-agent | `qwen3:4b` | `qwen3:4b` | On |
| `qwen4b_strong_planner_multi` | Multi-agent | `qwen3:4b` | `qwen3:30b-a3b` | On |
| `qwen4b_strong_planner_single` | Single-agent | `qwen3:4b` | `qwen3:30b-a3b` | On |
| `no_self_improvement_multi` | Multi-agent | Repository baseline | `gpt-5.5` | Off |
| `no_self_improvement_single` | Single-agent | Repository baseline | `gpt-5.5` | Off |
| `baseline_gpt5_mini` | Multi-agent | `gpt-5-mini` | `gpt-5-mini` | On |
| `single_agent_gpt5_mini` | Single-agent | `gpt-5-mini` | `gpt-5-mini` | On |

The uniform Qwen arms isolate topology. The strong-planner arms then measure
whether additional planning capacity changes either topology. The
no-self-improvement arms retain the episode-start planner and periodic watcher
inside every episode. They skip the planner LLM close-out, commit only the
deterministic episode boundary, restore byte-identical playbooks, clear
plans/trials/status/scratchpads, hide prior episode telemetry, and open fresh
player/planner/watcher sessions.

`gpt-5.1-mini` is not a supported OpenAI API model identifier. The runnable
historical small-model arms therefore use the actual `gpt-5-mini` model. OpenAI
marks it deprecated with a shutdown date of December 11, 2026; do not silently
replace it in this study after that date. See the
[GPT-5 Mini model page](https://developers.openai.com/api/docs/models/gpt-5-mini)
and [deprecation schedule](https://developers.openai.com/api/docs/deprecations).

## Prerequisites

Configure the normal MAPS simulator and Python environment, then authenticate
W&B and OpenAI:

```bash
source venv/bin/activate
python -m pip install -r requirements.txt
wandb login
export WANDB_PROJECT=maps-park-ablations
export WANDB_ENTITY=<your-wandb-entity>
export OPENAI_API_KEY=<your-openai-key>
```

On the 64 GB M4 Max, prepare Ollama:

```bash
ollama pull qwen3:4b
ollama pull qwen3:30b-a3b
ollama serve
```

When Studio runs on another machine, point it at the Mac:

```bash
export OLLAMA_BASE_URL=http://<mac-private-address>:11434
```

Keep a remote Ollama endpoint on a trusted private network; it should not be
exposed directly to the public internet.

## Move the Qwen system to the M4 Max

The Qwen treatments need the complete Studio and MAPS simulator source trees.
Create one portable bundle containing both systems and all four Qwen arms:

```bash
python scripts/create_qwen_transfer_bundle.py \
  --maps-repo ~/MAPs \
  --destination ../maps-qwen-m4-transfer \
  --archive
```

Move `maps-qwen-m4-transfer.tar.gz` to the Mac, extract it, and follow its
`README.md`. The bundle excludes credentials, Git metadata, virtual
environments, installed Node modules, logs, and experiment state. On the Mac,
`run_qwen_study.sh` runs only the four Qwen arms for 40 total episodes.

The other four treatments can run in separate local Git repositories. Create
the four repositories once (the virtual environment is shared by symlink):

```bash
apps/maps_park/create_non_qwen_ablation_repos.sh
```

There is no supervisor. Open four terminals and start one repository in each:

```bash
(cd ../maps-non-qwen-ablation-repos-v2/no_self_improvement_multi && \
  apps/maps_park/run_replica_ablation.sh --fresh)

(cd ../maps-non-qwen-ablation-repos-v2/no_self_improvement_single && \
  apps/maps_park/run_replica_ablation.sh --fresh)

(cd ../maps-non-qwen-ablation-repos-v2/baseline_gpt5_mini && \
  apps/maps_park/run_replica_ablation.sh --fresh)

(cd ../maps-non-qwen-ablation-repos-v2/single_agent_gpt5_mini && \
  apps/maps_park/run_replica_ablation.sh --fresh)
```

Each command is independent. Starting all four terminals gives parallel
execution without a parent launcher.

## Run individual arms

Each launcher defaults to a fresh ten-episode run when neither `--fresh` nor
`--resume` is supplied:

```bash
apps/maps_park/run_study_qwen4b_multi.sh
apps/maps_park/run_study_qwen4b_single.sh
apps/maps_park/run_study_qwen4b_strong_planner_multi.sh
apps/maps_park/run_study_qwen4b_strong_planner_single.sh
apps/maps_park/run_study_no_self_improvement_multi.sh
apps/maps_park/run_study_no_self_improvement_single.sh
apps/maps_park/run_small_model_baseline.sh
apps/maps_park/run_single_agent_gpt5_mini.sh
```

Resume only the same interrupted treatment:

```bash
apps/maps_park/run_study_qwen4b_multi.sh --resume
```

Run the complete 80-episode matrix sequentially with:

```bash
apps/maps_park/run_maps_ablation_study.sh
```

When Qwen is running on the Mac, start each API-backed replica manually on this
machine using the four commands above.

Every study launcher performs live preflight before the first model call. It
checks authenticated online W&B access and verifies the required OpenAI model or
Ollama tags. `MAPS_WANDB_REQUIRED=1` makes telemetry failures stop the experiment
instead of silently continuing with local-only results.

## Optional separate repository replicas

Create all eight local Git repositories from the current working tree:

```bash
python scripts/create_maps_ablation_replicas.py \
  --destination ../maps-ablation-replicas \
  --link-venv
```

Omit `--link-venv` when moving the repositories to another computer, then build
a virtual environment in each destination. To create only one treatment:

```bash
python scripts/create_maps_ablation_replicas.py \
  --destination ../maps-ablation-replicas \
  --arm qwen4b_strong_planner_multi
```

The generator copies the current workspace, excluding credentials, Git history,
virtual environments, caches, and runtime state. It refuses to overwrite an
existing destination. Each replica receives an ignored
`.ablation-instance.env`, a committed treatment description, a fresh local Git
history, and unique default ports. Run a replica with:

```bash
apps/maps_park/run_replica_ablation.sh
```

The authoritative matrix is
[`config/maps_ablation_study.json`](../config/maps_ablation_study.json). W&B run
configuration records the study ID, arm, topology, self-improvement flag,
provider, role-specific models, context size, and ten-episode limit.
