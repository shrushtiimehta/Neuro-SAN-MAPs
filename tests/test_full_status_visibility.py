"""The baseline coordinator can read the complete status snapshot directly."""

from __future__ import annotations

import json
from pathlib import Path

from apps.maps_park.validate_ablations import _load
from coded_tools import park_status

ROOT = Path(__file__).resolve().parents[1]


def test_full_status_is_written_alongside_domain_slices(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    snapshot = {"step": 7, "cash": 1234, "placed_rides": [], "guests": {"total": 99}}

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    assert json.loads((tmp_path / "status_full.json").read_text()) == snapshot
    assert not (tmp_path / "status_coordinator.json").exists()
    assert all(
        (tmp_path / f"status_{name}.json").is_file()
        for name in park_status._SPECIALIST_FIELDS
        if name != "coordinator"
    )


def test_rides_status_includes_profit_and_park_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    snapshot = {
        "step": 7,
        "cash": 1234,
        "park_rating": 42,
        "park_value": 500,
        "park_capacity": 80,
        "avg_intensity": 4.5,
        "num_rides": 6,
        "ride_revenue": 1250,
        "ride_op_cost": 275,
        "out_of_service": False,
        "placed_rides": [
            {
                "subtype": "carousel",
                "subclass": "yellow",
                "x": 1,
                "y": 8,
                "revenue_generated": 240,
                "operating_cost": 30,
            }
        ],
        "available_entities": {},
        "broken_rides": [],
        "guests": {
            "total_guests": 100,
            "avg_money_spent": 25.5,
            "avg_time_in_park": 18.0,
            "avg_rides_visited": 2.5,
            "avg_food_shops_visited": 1.0,
        },
        "next_unlock": None,
    }

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    rides = json.loads((tmp_path / "status_rides.json").read_text())
    assert rides["park_value"] == 500
    assert rides["num_rides"] == 6
    assert rides["ride_revenue"] == 1250
    assert rides["ride_op_cost"] == 275
    assert list(rides).index("ride_op_cost") < list(rides).index("available_entities")
    assert list(rides).index("next_unlock") < list(rides).index("placed_rides")
    assert rides["guests"] == {
        "total_guests": 100,
        "avg_money_spent": 25.5,
        "avg_time_in_park": 18.0,
        "avg_rides_visited": 2.5,
    }
    assert rides["placed_rides"][0]["revenue_generated"] == 240
    assert "operating_cost" not in rides["placed_rides"][0]
    assert "out_of_service" not in rides


def test_shops_status_includes_profit_and_park_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    snapshot = {
        "step": 7,
        "cash": 1234,
        "park_rating": 42,
        "park_value": 500,
        "num_shops": 3,
        "shop_revenue": 900,
        "shop_op_cost": 120,
        "shops_out_of_service": True,
        "placed_shops": [],
        "available_entities": {},
        "guests": {
            "total_guests": 100,
            "avg_rides_visited": 2.5,
            "avg_food_shops_visited": 1.0,
        },
        "next_unlock": None,
    }

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    shops = json.loads((tmp_path / "status_shops.json").read_text())
    assert shops["park_value"] == 500
    assert shops["num_shops"] == 3
    assert shops["shop_revenue"] == 900
    assert shops["shop_op_cost"] == 120
    assert shops["out_of_service"] is True
    assert list(shops).index("out_of_service") < list(shops).index("available_entities")
    assert list(shops).index("next_unlock") < list(shops).index("placed_shops")
    assert shops["guests"] == {
        "total_guests": 100,
        "avg_food_shops_visited": 1.0,
    }
    assert "avg_rides_visited" not in shops["guests"]


def test_staff_status_includes_staff_count(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    snapshot = {
        "step": 7,
        "cash": 1234,
        "park_rating": 42,
        "park_value": 500,
        "num_staff": 5,
        "staff_op_cost": 240,
        "out_of_service": False,
        "min_uptime": 1.0,
        "min_cleanliness": 0.9,
        "placed_staff": [],
        "available_entities": {},
        "guests": {
            "total_guests": 100,
            "avg_money_spent": 25.5,
            "avg_time_in_park": 18.0,
        },
        "next_unlock": None,
    }

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    staff = json.loads((tmp_path / "status_staff.json").read_text())
    assert staff["park_value"] == 500
    assert staff["num_staff"] == 5
    assert staff["staff_op_cost"] == 240
    assert staff["guests"] == {
        "total_guests": 100,
        "avg_money_spent": 25.5,
        "avg_time_in_park": 18.0,
    }
    assert list(staff).index("min_cleanliness") < list(staff).index("available_entities")
    assert list(staff).index("next_unlock") < list(staff).index("placed_staff")


def test_research_status_includes_exact_progress(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    progress = {
        "target_subtype": "carousel",
        "target_tier": "blue",
        "turns_remaining": 3,
    }
    snapshot = {
        "step": 7,
        "horizon": 100,
        "cash": 1234,
        "daily_profit": 50,
        "asset_investment": 0,
        "park_rating": 42,
        "park_value": 500,
        "research_speed": "slow",
        "research_topics": ["carousel"],
        "research_progress": progress,
        "research_operating_cost": 250,
        "available_entities": {},
        "next_unlock": None,
    }

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    research = json.loads((tmp_path / "status_research.json").read_text())
    assert research["research_progress"] == progress


def test_layout_status_includes_compact_counts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    snapshot = {
        "step": 7,
        "park_rating": 42,
        "num_rides": 6,
        "num_shops": 3,
        "num_staff": 5,
        "num_empty_reachable_tiles": 8,
        "num_empty_unreachable_tiles": 12,
        "num_water_adjacent_tiles": 4,
        "num_ride_placement_tiles": 20,
        "num_shop_placement_tiles": 8,
        "reachable_tiles": [],
        "water_adjacent": [],
        "unreachable_tiles": [],
        "path_coords": [],
        "placed_rides": [
            {
                "subtype": "carousel",
                "subclass": "yellow",
                "x": 1,
                "y": 8,
                "revenue_generated": 240,
                "operating_cost": 30,
            }
        ],
        "placed_shops": [],
        "placed_staff": [],
        "entrance": [0, 0],
        "exit": [19, 19],
    }

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    layout = json.loads((tmp_path / "status_layout.json").read_text())
    assert list(layout)[:10] == [
        "step",
        "park_rating",
        "num_rides",
        "num_shops",
        "num_staff",
        "num_empty_reachable_tiles",
        "num_empty_unreachable_tiles",
        "num_water_adjacent_tiles",
        "num_ride_placement_tiles",
        "num_shop_placement_tiles",
    ]
    assert layout["num_rides"] == 6
    assert layout["num_shops"] == 3
    assert layout["num_staff"] == 5
    assert layout["num_empty_reachable_tiles"] == 8
    assert layout["num_empty_unreachable_tiles"] == 12
    assert layout["num_water_adjacent_tiles"] == 4
    assert layout["num_ride_placement_tiles"] == 20
    assert layout["num_shop_placement_tiles"] == 8
    assert layout["placed_rides"][0]["revenue_generated"] == 240
    assert "operating_cost" not in layout["placed_rides"][0]
    assert "num_path_tiles" not in layout


def test_full_status_is_written_in_merged_mode(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", True)
    snapshot = {"step": 8, "cash": 2345}

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    assert json.loads((tmp_path / "status_full.json").read_text()) == snapshot
    assert json.loads((tmp_path / "status_solo.json").read_text()) == snapshot


def test_filtered_coordinator_status_remains_ablation_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(park_status, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(park_status, "MERGED_CONTEXT", False)
    monkeypatch.setenv("MAPS_ARM_NAME", "full_status_subagents")
    snapshot = {"step": 7, "cash": 1234, "guests": {"total": 99}}

    park_status.ParkStatus()._write_specialist_snapshots(snapshot)

    coordinator = json.loads((tmp_path / "status_coordinator.json").read_text())
    assert coordinator["step"] == 7
    assert "guests" not in coordinator


def test_baseline_strategy_coordinator_reads_status_full() -> None:
    config = _load(ROOT / "registries" / "player.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}

    assert "state_read(name='status_full')" in tools["strategy_coordinator"]["instructions"]
    reader = tools["state_read"]
    assert reader["args"]["name_map"]["status_full"].endswith("/status_full.json")
    assert "status_full" in reader["function"]["parameters"]["properties"]["name"]["enum"]


def test_baseline_watcher_reads_status_full() -> None:
    config = _load(ROOT / "registries" / "watcher.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}

    assert "state_read('status_full')" in tools["mid_episode_analyst"]["instructions"]
    reader = tools["state_read"]
    assert reader["args"]["name_map"]["status_full"].endswith("/status_full.json")
    assert "status_coordinator" not in reader["args"]["name_map"]
