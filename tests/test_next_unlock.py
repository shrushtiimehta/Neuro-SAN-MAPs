"""Check ParkStatus._next_unlock ETA arithmetic against the MAPs research rules."""

from coded_tools.park_status import ParkStatus


def _obs(speed="slow", slow=0, medium=0, fast=0, unlocked=None, topics=None):
    return {
        "research_speed": speed,
        "slow_days_since_last_new_entity": slow,
        "medium_days_since_last_new_entity": medium,
        "fast_days_since_last_new_entity": fast,
        "available_entities": unlocked if unlocked is not None else {"carousel": ["yellow"]},
        "research_topics": topics,
    }


def test_next_unlock():
    nu = ParkStatus()._next_unlock

    # blue needs 100 points; slow buys 25/day -> 4 days from scratch, 1 day after 3 days spent.
    assert nu(_obs()) == {"tier": "blue", "days": 4, "subtypes": ["carousel"]}
    assert nu(_obs(slow=3)) == {"tier": "blue", "days": 1, "subtypes": ["carousel"]}
    # Mixed speeds sum as points: 1 fast (100) already clears blue.
    assert nu(_obs(fast=1)) == {"tier": "blue", "days": 0, "subtypes": ["carousel"]}
    # fast buys 100/day -> red (400) takes 4 days.
    assert nu(_obs(speed="fast", unlocked={"carousel": ["yellow", "blue", "green"]})) == {
        "tier": "red",
        "days": 4,
        "subtypes": ["carousel"],
    }
    # Breadth-first: one topic still missing blue keeps the tier at blue, and only
    # the subtypes missing THAT tier are listed (carousel already has blue).
    assert nu(_obs(unlocked={"carousel": ["yellow", "blue"], "food": ["yellow"]})) == {
        "tier": "blue",
        "days": 4,
        "subtypes": ["food"],
    }
    # Several subtypes at the same tier: all listed, `days` is the ETA for the first.
    assert nu(_obs(unlocked={"carousel": ["yellow"], "food": ["yellow"]}))["subtypes"] == [
        "carousel",
        "food",
    ]
    # research_topics narrows it: only listed subtypes can be the pending unlock.
    assert nu(_obs(unlocked={"carousel": ["yellow"], "food": ["yellow"]}, topics=["food"]))[
        "subtypes"
    ] == ["food"]

    # No research running, and nothing left to unlock -> no ETA.
    assert nu(_obs(speed="none")) is None
    assert nu(_obs(unlocked={"carousel": ["yellow", "blue", "green", "red"]})) is None
    # Topics naming a subtype absent from the ledger are ignored, not treated as locked.
    assert nu(_obs(unlocked={"carousel": ["yellow", "blue", "green", "red"]}, topics=["mystery"])) is None


if __name__ == "__main__":
    test_next_unlock()
    print("ok")
