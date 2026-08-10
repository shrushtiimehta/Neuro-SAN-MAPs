"""The BEST unlocked tier may never LAND on an unreachable tile.

Guests never walk to a stranded tile, so whatever sits there earns $0 for the
rest of the run. The top tier belongs on a free_tile — evicting a weaker
reachable ride with a (free) `move` if need be. Anything below the top tier is
allowed. Enforced on both the `place` destination and the `move` destination.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coded_tools.propose_action import ProposeAction  # noqa: E402

OBS = {
    "valid_placement_coords": [[5, 5]],
    "unreachable_tiles": [[9, 9]],
    "available_entities": {"carousel": ["yellow", "blue", "green"], "food": ["yellow"]},
    "rides": {"ride_list": [{"x": 1, "y": 1, "subtype": "carousel", "subclass": "blue"}]},
}


def place(**args):
    return ProposeAction()._check_placement_tile({"type": "ride", **args}, OBS)


def move(**args):
    return ProposeAction()._check_move_fields(
        {"type": "ride", "subtype": "carousel", "x": 1, "y": 1, **args}, OBS)


def test_place():
    assert place(subtype="carousel", subclass="green", x=5, y=5)[0]     # top tier, reachable
    assert place(subtype="carousel", subclass="yellow", x=9, y=9)[0]    # tier-1, stranded
    assert place(subtype="carousel", subclass="blue", x=9, y=9)[0]      # mid tier, stranded: allowed
    ok, why = place(subtype="carousel", subclass="green", x=9, y=9)     # TOP tier, stranded
    assert not ok and "unreachable" in why and "free_tile" in why
    # Nothing better exists yet -> no restriction.
    assert place(type="shop", subtype="food", subclass="yellow", x=9, y=9)[0]
    assert not place(subtype="carousel", subclass="yellow", x=0, y=0)[0]  # not buildable at all


def test_move():
    assert move(subclass="yellow", new_x=9, new_y=9)[0]        # evicting a weak tier is the point
    assert move(subclass="blue", new_x=9, new_y=9)[0]          # mid tier stranded: allowed
    assert move(subclass="green", new_x=5, new_y=5)[0]         # top tier onto a free tile
    ok, why = move(subclass="green", new_x=9, new_y=9)         # TOP tier stranded by move
    assert not ok and "unreachable" in why
    ok, why = move(new_x=5, new_y=5)                           # subclass omitted
    assert not ok and "subclass" in why


if __name__ == "__main__":
    test_place()
    test_move()
    print("ok")
