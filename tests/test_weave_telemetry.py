import datetime as dt

from coded_tools import weave_telemetry


class FakeClient:
    def __init__(self):
        self.created = []
        self.finished = []

    def create_call(self, **kwargs):
        call = type("Call", (), {})()
        call.summary = None
        self.created.append((call, kwargs))
        return call

    def finish_call(self, call, **kwargs):
        self.finished.append((call, kwargs))


def test_episode_and_turn_calls_use_live_compatible_shape():
    client = FakeClient()
    started = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
    parent = weave_telemetry.create_episode_call(
        client,
        run_metadata={"wandb_run_id": "abc", "ablation_arm": "solo"},
        episode_index=0,
        started_at=started,
        historical=True,
        call_id="root-id",
    )
    record = {
        "wall_time": started.timestamp() + 5,
        "turn": 1,
        "attempts": 2,
        "turn_done": True,
        "proposed": {"action": "wait"},
        "verified_after": {"episode": 0, "step": 1, "cumulative_reward": 10},
        "tokens": {"total_tokens": 12, "total_cost": 0.1, "time_taken_in_seconds": 5},
    }
    child = weave_telemetry.create_turn_call(
        client,
        parent=parent,
        run_metadata={"wandb_run_id": "abc", "ablation_arm": "solo"},
        episode_index=0,
        record=record,
        historical=True,
        call_id="child-id",
    )
    weave_telemetry.finish_episode_call(
        client,
        parent,
        last_step=record["verified_after"],
        episode_summary={"final_reward": 10},
        complete=True,
        turn_count=1,
    )

    assert client.created[0][1]["op"] == "maps_park.episode"
    assert client.created[0][1]["inputs"]["episode"] == 1
    assert client.created[1][1]["op"] == "maps_park.turn"
    assert client.created[1][1]["inputs"]["turn_record"] == record
    assert child.summary["maps"]["tokens"] == 12
    assert client.finished[-1][1]["output"]["status"] == "complete"


def test_episode_display_name_is_concise():
    assert (
        weave_telemetry.episode_display_name({"trace_label": "Embedded", "run_number": 1}, 0)
        == "Embedded • Run 1 • Episode 1"
    )
    assert weave_telemetry.episode_display_name({"ablation_arm": "planner_only"}, 2) == "Planner • Run 1 • Episode 3"
