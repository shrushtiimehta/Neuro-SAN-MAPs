"""Placements the env rejects must be caught BEFORE they cost a turn.

Both holes are taken from real run logs:

  1. `Invalid location for staff. Must be on a path or in an attraction.` — the
     most common env rejection in the run (5 turns). `move` checked the staff
     tile rule; `place` did not check at all.
  2. `Tile already contains a ride.` — occupancy was only ever inferred from
     valid_placement_coords, which the env reports EMPTY once the park is full.
     That is exactly the late game where every free tile is already taken, so
     the check went silent when it mattered most (ep0 steps 83/93, both moves).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coded_tools.propose_action import ProposeAction  # noqa: E402

# A full park: the env has stopped reporting anywhere to build.
FULL = {
    "valid_placement_coords": [],
    "unreachable_tiles": [],
    "path_coords": [[9, 1], [9, 2]],
    "rides": {"ride_list": [{"x": 7, "y": 10, "subtype": "carousel", "subclass": "yellow"}]},
    "shops": {"shop_list": [{"x": 8, "y": 10, "subtype": "food", "subclass": "yellow"}]},
    "staff": {"staff_list": [{"x": 9, "y": 1, "subtype": "janitor", "subclass": "yellow"}]},
}


def place(**args):
    return ProposeAction()._check_placement_tile(args, FULL)


def test_occupied_tile_is_caught_without_valid_placement_coords():
    ok, why = place(type="ride", subtype="carousel", subclass="yellow", x=7, y=10)
    assert not ok and "already contains" in why, why
    # A shop tile blocks a ride and vice versa — one attraction per tile.
    assert not place(type="ride", subtype="carousel", subclass="yellow", x=8, y=10)[0]
    # A free tile still passes: with no valid_placement_coords the env decides.
    assert place(type="ride", subtype="carousel", subclass="yellow", x=3, y=3)[0]


def test_staff_placement_obeys_the_path_rule():
    assert place(type="staff", subtype="janitor", subclass="yellow", x=9, y=1)[0]   # path tile
    assert place(type="staff", subtype="mechanic", subclass="yellow", x=7, y=10)[0]  # in a ride
    # (0,0) is neither — the exact coordinate the layout planner emitted twice.
    ok, why = place(type="staff", subtype="mechanic", subclass="yellow", x=0, y=0)
    assert not ok and "staff must be" in why, why


def test_move_destination_is_checked_the_same_way():
    def move(**args):
        return ProposeAction()._check_move_fields(
            {"subtype": "carousel", "subclass": "yellow", "x": 7, "y": 10, **args}, FULL)

    ok, why = move(type="ride", new_x=8, new_y=10)      # ep0 step 83/93
    assert not ok and "already contains" in why, why
    ok, why = move(type="ride", new_x=7, new_y=10)      # moving onto itself
    assert not ok and "changes nothing" in why, why
    ok, why = move(type="staff", x=9, y=1, new_x=0, new_y=0)
    assert not ok and "staff must be" in why, why


if __name__ == "__main__":
    test_occupied_tile_is_caught_without_valid_placement_coords()
    test_staff_placement_obeys_the_path_rule()
    test_move_destination_is_checked_the_same_way()
    print("ok")