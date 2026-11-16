"""Check ParkStatus._next_unlock ETA handling against the MAPs research rules."""

from coded_tools.park_status import ParkStatus
from coded_tools.research_progress import normalize_research_progress


def _obs(speed="slow", entity="carousel", color="blue", turns=4, unlocked=None, topics=None):
    """An observation carrying the sim's live research counters.

    `research_progress` is forwarded by maps_mcp_server straight from the full
    state, so `turns_remaining` is the exact ETA for the tier being researched.
    """
    progress = None
    if entity is not None:
        progress = {
            "target_subtype": entity,
            "target_tier": color,
            "turns_remaining": turns,
        }
    return {
        "research_speed": speed,
        "research_progress": progress,
        "available_entities": unlocked if unlocked is not None else {"carousel": ["yellow"]},
        "research_topics": topics,
    }


def test_next_unlock():
    nu = ParkStatus()._next_unlock

    # The server reports the exact four-turn ETA.
    assert nu(_obs()) == {"subtype": "carousel", "tier": "blue", "days": 4, "subtypes": ["carousel"]}
    assert nu(_obs(turns=1))["days"] == 1
    assert nu(_obs(turns=2))["days"] == 2
    assert (
        nu(_obs(speed="fast", color="red", turns=4, unlocked={"carousel": ["yellow", "blue", "green"]}))["days"] == 4
    )
    # The pending unlock is whatever the sim's cursor sits on, whatever domain.
    assert (
        nu(_obs(entity="janitor", color="green", turns=4, speed="medium", unlocked={"janitor": ["yellow", "blue"]}))[
            "days"
        ]
        == 4
    )

    # subtypes: the round-robin queue still owed THIS tier. carousel already has
    # blue, so it drops out; the cursor's own subtype leads the rest.
    assert nu(
        _obs(
            entity="food",
            unlocked={
                "carousel": ["yellow", "blue"],
                "food": ["yellow"],
                "drink": ["yellow"],
            },
        )
    )["subtypes"] == ["food", "drink"]
    # Rotated to start at the cursor, not at the ledger's first key.
    assert nu(
        _obs(
            entity="drink",
            unlocked={
                "carousel": ["yellow"],
                "drink": ["yellow"],
                "food": ["yellow"],
            },
        )
    )["subtypes"] == ["drink", "food", "carousel"]
    # research_topics narrows the queue to the listed subtypes only.
    assert nu(
        _obs(
            entity="food",
            topics=["food"],
            unlocked={
                "carousel": ["yellow"],
                "food": ["yellow"],
            },
        )
    )["subtypes"] == ["food"]

    # Research off, or every listed topic already unlocked (the sim leaves the
    # research target undefined in both cases) -> no ETA.
    assert nu(_obs(speed="none")) is None
    assert nu(_obs(entity=None)) is None
    # A backend hiccup drops research_progress entirely; never crash the turn.
    assert nu({"research_speed": "fast"}) is None
    assert nu({"research_speed": "fast", "research_progress": {}}) is None

    # Existing cached observations using the old names and point counts remain readable.
    assert (
        nu(
            {
                "research_speed": "slow",
                "research_progress": {
                    "current_entity": "carousel",
                    "current_color": "blue",
                    "points_remaining": 25,
                },
                "available_entities": {"carousel": ["yellow"]},
            }
        )["days"]
        == 1
    )

    converted = normalize_research_progress(
        {
            "current_entity": "carousel",
            "current_color": "blue",
            "points_remaining": 26,
        },
        "slow",
    )
    assert converted == {
        "target_subtype": "carousel",
        "target_tier": "blue",
        "turns_remaining": 2,
    }


if __name__ == "__main__":
    test_next_unlock()
    print("ok")
