# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT
"""Canonical financial metrics for MAPs action results.

The simulator's observation ``profit`` is revenue minus every expense charged
on that step.  A successful ride/shop placement therefore makes that number
look like a recurring operating loss even though most of the drop is a one-time
construction investment. This module keeps that source value internal and
exposes only the construction-adjusted ``daily_profit``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from coded_tools.finance_gate import _RIDES_ECONOMICS_PATH
from coded_tools.finance_gate import _SHOPS_ECONOMICS_PATH
from coded_tools.finance_gate import _read_lookup_lines


class FinancialMetrics:
    """Calculate canonical financial values from simulator results."""

    @staticmethod
    @lru_cache(maxsize=2)
    def _economics(domain: str) -> dict[tuple[str, str, str], dict[str, Any]]:
        """Load and cache the economics table for a buildable entity domain."""
        path = _RIDES_ECONOMICS_PATH if domain == "rides" else _SHOPS_ECONOMICS_PATH
        return _read_lookup_lines(path, domain)

    @staticmethod
    def construction_asset_investment(action: Any, action_args: Any) -> int | float:
        """Return the build cost for a proposed ride/shop placement, else zero."""
        if str(action or "").lower() != "place" or not isinstance(action_args, dict):
            return 0
        entity_type = str(action_args.get("type") or "").lower()
        if entity_type not in {"ride", "shop"}:
            return 0
        domain = entity_type + "s"
        subtype = str(action_args.get("subtype") or "").lower()
        subclass = str(action_args.get("subclass") or "").lower()
        value = FinancialMetrics._economics(domain).get((domain, subtype, subclass), {}).get("building_cost", 0)
        return value if FinancialMetrics._is_number(value) and value >= 0 else 0

    @staticmethod
    def financial_metrics(
        envelope: dict[str, Any], observation: dict[str, Any] | None = None
    ) -> dict[str, int | float | None]:
        """Split raw simulator cash flow from investment and operating profit.

        ``daily_profit`` is the recurring result after adding one-time construction
        investment back. Research remains included because it is a daily operating
        expense and is already reported separately as ``research_operating_cost``.
        """
        obs = observation if isinstance(observation, dict) else envelope.get("observation")
        obs = obs if isinstance(obs, dict) else {}
        raw_profit = FinancialMetrics._number(obs.get("profit"))
        asset_investment = FinancialMetrics._number(envelope.get("asset_investment")) or 0
        daily_profit = raw_profit + asset_investment if raw_profit is not None else None
        return {
            "asset_investment": asset_investment,
            "daily_profit": daily_profit,
        }

    @staticmethod
    def _number(value: Any) -> int | float | None:
        """Convert a supported numeric value while rejecting booleans."""
        if FinancialMetrics._is_number(value):
            return value
        if isinstance(value, str):
            try:
                parsed = float(value.strip())
            except ValueError:
                return None
            return int(parsed) if parsed.is_integer() else parsed
        return None

    @staticmethod
    def _is_number(value: Any) -> bool:
        """Return whether a value is a supported non-boolean number."""
        return isinstance(value, (int, float)) and not isinstance(value, bool)


# Keep the established function API while the implementation lives in one class.
construction_asset_investment = FinancialMetrics.construction_asset_investment
financial_metrics = FinancialMetrics.financial_metrics
