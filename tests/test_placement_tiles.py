"""Check make_concise_obs splits buildable tiles into reachable vs stranded.

Grid: a path from the entrance along row 0, plus a DISCONNECTED path island at
(5,5). Tiles beside the island are path-adjacent (the env accepts a build) but
no guest can walk there — that is exactly `unreachable_tiles`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "maps_park"))
from maps_mcp_server import make_concise_obs  # noqa: E402

OBS = {
    "entrance": [0, 0],
    "exit": [3, 0],
    "paths": [{"x": x, "y": 0} for x in range(4)] + [{"x": 5, "y": 5}],
    # (1,1) touches BOTH (1,2) and (0,1) -> +2; (3,1) and (4,0) touch (4,1) -> +1.
    "waters": [{"x": 1, "y": 2}, {"x": 0, "y": 1}, {"x": 4, "y": 1}],
    # (2,1) touches the entrance path; (5,4) touches the island only.
    "rides": {"ride_list": [{"x": 2, "y": 1}, {"x": 5, "y": 4}]},
    "shops": {"shop_list": []},
    "staff": {"staff_list": []},
}


def test_tiles():
    obs = make_concise_obs(OBS)
    free = {tuple(c) for c in obs["valid_placement_coords"]}
    stranded = {tuple(c) for c in obs["unreachable_tiles"]}
    water_adj = [(c["x"], c["y"], c["water"]) for c in obs["water_adjacent"]]

    assert (1, 1) in free                      # beside the reachable path
    assert (2, 1) not in free                  # occupied by a ride
    assert (1, 2) not in free                  # water is not buildable
    assert stranded == {(4, 5), (6, 5), (5, 6)}   # around the island, minus the built-on (5,4)
    assert not (free & stranded)               # the two sets never overlap
    # A built-on tile leaves both lists, so the flag is the only stranded tell.
    assert [r["reachable"] for r in obs["rides"]["ride_list"]] == [True, False]
    # Only free tiles touching water; bonus STACKS and the list is best-first.
    assert water_adj == [(1, 1, 2), (3, 1, 1), (4, 0, 1)]
    assert {(x, y) for x, y, _ in water_adj} <= free


if __name__ == "__main__":
    test_tiles()
    print("ok")
