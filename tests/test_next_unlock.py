"""Check ParkStatus._next_unlock ETA arithmetic against the MAPs research rules."""

from coded_tools.park_status import ParkStatus


def _obs(speed="slow", entity="carousel", color="blue", remaining=100,
         unlocked=None, topics=None):
    """An observation carrying the sim's live research counters.

    `research_progress` is forwarded by maps_mcp_server straight from the full
    state, so `points_remaining` is what is actually left on the tier the sim is
    grinding — no reconstruction from the days-since-unlock counters.
    """
    progress = None
    if entity is not None:
        progress = {
            "current_entity": entity,
            "current_color": color,
            "points_remaining": remaining,
        }
    return {
        "research_speed": speed,
        "research_progress": progress,
        "available_entities": unlocked if unlocked is not None else {"carousel": ["yellow"]},
        "research_topics": topics,
    }


def test_next_unlock():
    nu = ParkStatus()._next_unlock

    # blue needs 100 points; slow buys 25/day -> 4 days from scratch.
    assert nu(_obs()) == {"subtype": "carousel", "tier": "blue", "days": 4,
                          "subtypes": ["carousel"]}
    # Banked points count: 25 left is one more slow day, not four.
    assert nu(_obs(remaining=25))["days"] == 1
    # A part-day of progress still costs a whole day — ceil, never floor.
    assert nu(_obs(remaining=26))["days"] == 2
    # fast buys 100/day -> red (400 points) takes 4 days.
    assert nu(_obs(speed="fast", color="red", remaining=400,
                   unlocked={"carousel": ["yellow", "blue", "green"]}))["days"] == 4
    # The pending unlock is whatever the sim's cursor sits on, whatever domain.
    assert nu(_obs(entity="janitor", color="green", remaining=200, speed="medium",
                   unlocked={"janitor": ["yellow", "blue"]}))["days"] == 4

    # subtypes: the round-robin queue still owed THIS tier. carousel already has
    # blue, so it drops out; the cursor's own subtype leads the rest.
    assert nu(_obs(entity="food", unlocked={
        "carousel": ["yellow", "blue"], "food": ["yellow"], "drink": ["yellow"],
    }))["subtypes"] == ["food", "drink"]
    # Rotated to start at the cursor, not at the ledger's first key.
    assert nu(_obs(entity="drink", unlocked={
        "carousel": ["yellow"], "drink": ["yellow"], "food": ["yellow"],
    }))["subtypes"] == ["drink", "food", "carousel"]
    # research_topics narrows the queue to the listed subtypes only.
    assert nu(_obs(entity="food", topics=["food"], unlocked={
        "carousel": ["yellow"], "food": ["yellow"],
    }))["subtypes"] == ["food"]

    # Research off, or every listed topic already unlocked (the sim leaves
    # current_entity undefined in both cases) -> no ETA.
    assert nu(_obs(speed="none")) is None
    assert nu(_obs(entity=None)) is None
    # A backend hiccup drops research_progress entirely; never crash the turn.
    assert nu({"research_speed": "fast"}) is None
    assert nu({"research_speed": "fast", "research_progress": {}}) is None


if __name__ == "__main__":
    test_next_unlock()
    print("ok")
