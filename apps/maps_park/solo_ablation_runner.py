"""Bounded Single Agent ablation runner.

The solo adapter owns the agent/session behavior. The bounded adapter adds
only the shared completed-episode limit.
"""

from __future__ import annotations

from apps.maps_park import bounded_runner

# Importing solo_runner first selects the isolated paths before runner loads.
from apps.maps_park import solo_runner


def main() -> None:
    """Run the solo arm with the standard bounded ablation lifecycle."""
    solo_runner._apply_solo_runtime()
    bounded_runner.main()


if __name__ == "__main__":
    main()
