"""Construction investment must not masquerade as a recurring operating loss."""

import asyncio

from apps.maps_park.runner import build_run_row
from coded_tools.action_dispatcher import ActionDispatcher
from coded_tools.financial_metrics import construction_asset_investment
from coded_tools.financial_metrics import financial_metrics
from coded_tools.latest_observation import LatestObservation
from coded_tools.park_status import ParkStatus


def test_green_carousel_build_is_asset_investment() -> None:
    action_args = {
        "type": "ride",
        "subtype": "carousel",
        "subclass": "green",
    }
    assert construction_asset_investment("place", action_args) == 11_500


def test_financial_metrics_split_construction_from_operations() -> None:
    envelope = {
        "asset_investment": 11_500,
        "observation": {"profit": -8_923, "research_operating_cost": 2_000},
    }

    assert financial_metrics(envelope) == {
        "asset_investment": 11_500,
        "daily_profit": 2_577,
    }


def test_non_construction_action_has_no_asset_investment() -> None:
    assert construction_asset_investment("wait", {}) == 0
    assert construction_asset_investment("place", {"type": "staff", "subtype": "janitor", "subclass": "yellow"}) == 0


def test_run_row_logs_all_financial_views() -> None:
    envelope = {
        "episode": 0,
        "step": 59,
        "done": False,
        "asset_investment": 11_500,
        "observation": {
            "money": 8_439,
            "profit": -8_923,
            "research_operating_cost": 2_000,
            "research_progress": {
                "target_subtype": "carousel",
                "target_tier": "blue",
                "turns_remaining": 3,
            },
            "rides": {"total_revenue_generated": 1_250},
            "shops": {"total_operating_cost": 120},
            "staff": {"total_operating_cost": 240},
        },
    }
    row = build_run_row({"action": "place", "args": {}}, envelope)

    assert row["asset_investment"] == 11_500
    assert row["daily_profit"] == 2_577
    assert row["ride_revenue"] == 1_250
    assert row["shop_op_cost"] == 120
    assert row["staff_op_cost"] == 240
    assert row["research_progress"]["turns_remaining"] == 3


def test_park_status_surfaces_corrected_profit(monkeypatch) -> None:
    async def fake_latest(self, args, sly_data):
        return {
            "window_size": 1,
            "latest": {
                "episode": 0,
                "step": 59,
                "asset_investment": 11_500,
                "observation": {
                    "step": 59,
                    "profit": -8_923,
                    "research_operating_cost": 2_000,
                    "research_progress": {
                        "target_subtype": "carousel",
                        "target_tier": "blue",
                        "turns_remaining": 3,
                    },
                    "min_cleanliness": 0.84,
                    "path_coords": [[1, 1], [1, 2]],
                    "valid_placement_coords": [[2, 2], [2, 3], [2, 4]],
                    "water_adjacent": [
                        {"x": 2, "y": 2, "water": 1},
                        {"x": 9, "y": 9, "water": 2},
                    ],
                    "unreachable_tiles": [[18, 18], [18, 19]],
                    "rides": {
                        "total_rides": 6,
                        "total_revenue_generated": 1250,
                        "total_operating_cost": 275,
                        "min_uptime": 1.0,
                    },
                    "shops": {
                        "total_shops": 3,
                        "total_revenue_generated": 900,
                        "total_operating_cost": 120,
                        "shop_list": [{"out_of_service": True}],
                    },
                    "staff": {
                        "total_operating_cost": 240,
                        "staff_list": [{"subtype": "janitor"}, {"subtype": "mechanic"}],
                    },
                },
            },
        }

    monkeypatch.setattr(LatestObservation, "async_invoke", fake_latest)
    monkeypatch.setattr(ParkStatus, "_write_specialist_snapshots", lambda self, snapshot: None)

    status = asyncio.run(ParkStatus().async_invoke({"park": "0"}, {}))
    assert status["asset_investment"] == 11_500
    assert status["daily_profit"] == 2_577
    assert status["num_rides"] == 6
    assert status["ride_revenue"] == 1250
    assert status["ride_op_cost"] == 275
    assert status["num_shops"] == 3
    assert status["shop_revenue"] == 900
    assert status["shop_op_cost"] == 120
    assert status["staff_op_cost"] == 240
    assert status["research_progress"]["turns_remaining"] == 3
    assert status["shops_out_of_service"] is True
    assert status["num_staff"] == 2
    assert status["min_uptime"] == 1.0
    assert status["min_cleanliness"] == 0.84
    assert status["num_empty_reachable_tiles"] == 3
    assert status["num_empty_unreachable_tiles"] == 2
    assert status["num_water_adjacent_tiles"] == 1
    assert status["water_adjacent"] == [{"x": 2, "y": 2, "water": 1}]
    assert status["num_ride_placement_tiles"] == 5
    assert status["num_shop_placement_tiles"] == 3
    assert "num_path_tiles" not in status
    assert "current_phase" not in status
    assert {
        "num_rides",
        "num_shops",
        "num_staff",
        "min_uptime",
        "min_cleanliness",
        "shop_revenue",
        "shop_op_cost",
        "ride_revenue",
        "ride_op_cost",
        "staff_op_cost",
        "asset_investment",
        "daily_profit",
        "research_progress",
    } <= status.keys()


def test_dispatcher_attaches_only_committed_investment(monkeypatch) -> None:
    class SuccessfulPlace:
        async def async_invoke(self, args, sly_data):
            return {"episode": 0, "step": 59, "observation": {"profit": -8_923}}

    class RejectedPlace:
        async def async_invoke(self, args, sly_data):
            return {
                "episode": 0,
                "step": 59,
                "error": "invalid placement",
                "observation": {"profit": 2_577},
            }

    async def ignore_cache(self, args, sly_data):
        return {"ok": True}

    args = {
        "park": 0,
        "action": "place",
        "args": {"type": "ride", "subtype": "carousel", "subclass": "green"},
    }
    monkeypatch.setattr(LatestObservation, "async_invoke", ignore_cache)
    monkeypatch.setitem(ActionDispatcher.ACTION_TABLE, "place", SuccessfulPlace)
    committed = asyncio.run(ActionDispatcher().async_invoke(args, {}))
    assert committed["asset_investment"] == 11_500

    monkeypatch.setitem(ActionDispatcher.ACTION_TABLE, "place", RejectedPlace)
    rejected = asyncio.run(ActionDispatcher().async_invoke(args, {}))
    assert rejected["asset_investment"] == 0
