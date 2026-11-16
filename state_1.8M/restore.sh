#!/usr/bin/env bash
# Put the park back on ep3's 1,861,276 strategy. Nothing here is generated:
# every file is a copy of what ep3 actually read. Run from the repo root.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
cp "$here"/playbook_*.md "$here"/episode_checklist.md "$here"/trial_strategies*.md \
   "$here"/plan_last_good.json "$here"/champion_reward.json coded_tools/state/
cp "$here"/plan_last_good.json coded_tools/state/plan_current.json
# ep7's live park — stale the moment a new run starts; ParkStatus rewrites them.
rm -f coded_tools/state/status_*.json coded_tools/state/latest_observations.json
echo "restored ep3 champion state (reward 1861276) into coded_tools/state/"
