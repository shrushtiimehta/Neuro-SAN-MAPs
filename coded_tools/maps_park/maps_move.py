# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
# Licensed under the Apache License, Version 2.0.
"""Typed wrapper for the MAPs ``move`` action."""

from __future__ import annotations

from coded_tools.maps_park.maps_action_base import MapsActionBase


class MapsMove(MapsActionBase):
    ACTION_NAME = "move"
    DSL_PARAM_ORDER = ("type", "subtype", "subclass", "x", "y", "new_x", "new_y")
