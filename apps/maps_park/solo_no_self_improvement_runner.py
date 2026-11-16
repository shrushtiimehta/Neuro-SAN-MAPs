"""Solo-topology entry point for the no-cross-episode MAPS control."""

from __future__ import annotations

from apps.maps_park import no_self_improvement_runner
from apps.maps_park import solo_runner


class SoloNoSelfImprovementRunner:
    """Select Solo paths, then apply the shared no-carryover lifecycle."""

    @staticmethod
    def main() -> None:
        """Run ten Solo episodes with full planning but no strategy carryover."""
        solo_runner._apply_solo_runtime()
        no_self_improvement_runner.NoSelfImprovementRunner.main()


if __name__ == "__main__":
    SoloNoSelfImprovementRunner.main()
