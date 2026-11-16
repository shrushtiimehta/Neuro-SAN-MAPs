#!/usr/bin/env bash
# Create four isolated non-Qwen repositories that share this checkout's venv.

set -euo pipefail

STUDIO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESTINATION="${1:-$STUDIO_ROOT/../maps-non-qwen-ablation-repos-v2}"

python3 "$STUDIO_ROOT/scripts/create_maps_ablation_replicas.py" \
    --destination "$DESTINATION" \
    --link-venv \
    --arm no_self_improvement_multi \
    --arm no_self_improvement_single \
    --arm baseline_gpt5_mini \
    --arm single_agent_gpt5_mini

echo
echo "Created four repositories under $DESTINATION"
echo "Start each command yourself in a separate terminal:"
echo "  (cd $DESTINATION/no_self_improvement_multi && apps/maps_park/run_replica_ablation.sh --fresh)"
echo "  (cd $DESTINATION/no_self_improvement_single && apps/maps_park/run_replica_ablation.sh --fresh)"
echo "  (cd $DESTINATION/baseline_gpt5_mini && apps/maps_park/run_replica_ablation.sh --fresh)"
echo "  (cd $DESTINATION/single_agent_gpt5_mini && apps/maps_park/run_replica_ablation.sh --fresh)"
