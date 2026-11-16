"""Central runtime roots for the MAPs benchmark arms."""

from __future__ import annotations

import os

MERGED_CONTEXT = os.environ.get("MAPS_MERGED_CONTEXT", "0").strip().lower() in {"1", "true", "yes", "on"}
USE_LAST_REWARD = os.environ.get("MAPS_USE_LAST_REWARD", "1").strip().lower() in {"1", "true", "yes", "on"}
STATE_DIR = os.environ.get("MAPS_STATE_DIR", "state")
DEFAULT_SEED_DIR = (
    os.path.join("coded_tools", "ablations", "single_agent", "config_files")
    if MERGED_CONTEXT
    else os.path.join("coded_tools", "config_files")
)
SEED_DIR = os.environ.get("MAPS_SEED_DIR", DEFAULT_SEED_DIR)
LOG_DIR = os.environ.get("MAPS_LOG_DIR", os.path.join("logs", "maps_park"))


class StateDir:
    """Build paths below the active benchmark arm's runtime roots."""

    @staticmethod
    def state_path(*parts: str) -> str:
        """Return a path below the active arm's state root."""
        return os.path.join(STATE_DIR, *parts)

    @staticmethod
    def log_path(*parts: str) -> str:
        """Return a path below the active arm's log root."""
        return os.path.join(LOG_DIR, *parts)


# Keep the established function API while the implementation lives in one class.
state_path = StateDir.state_path
log_path = StateDir.log_path
