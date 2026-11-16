#!/usr/bin/env bash
set -euo pipefail

STUDIO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GMEMORY_REPO="${MAPS_GMEMORY_REPO:-$HOME/GMemory-upstream}"
GMEMORY_COMMIT=7b581c51d993bd600df14691d101d7e601040cc6

if [[ ! -d "$GMEMORY_REPO/.git" ]]; then
    git clone https://github.com/bingreeky/GMemory.git "$GMEMORY_REPO"
fi
git -C "$GMEMORY_REPO" fetch origin "$GMEMORY_COMMIT"
git -C "$GMEMORY_REPO" checkout --detach "$GMEMORY_COMMIT"

"$STUDIO_DIR/venv/bin/pip" install \
    -r "$STUDIO_DIR/coded_tools/ablations/g_memory_player_planner_watcher/requirements.txt"
"$STUDIO_DIR/venv/bin/python" -c \
    'from sentence_transformers import SentenceTransformer; SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")'
echo "GMemory upstream checkout ready at $GMEMORY_COMMIT"
