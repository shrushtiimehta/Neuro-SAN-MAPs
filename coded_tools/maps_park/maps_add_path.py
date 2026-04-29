# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
# Licensed under the Apache License, Version 2.0.
"""Typed wrapper for the MAPs ``add_path`` action."""

from __future__ import annotations

from coded_tools.maps_park.maps_action_base import MapsActionBase


class MapsAddPath(MapsActionBase):
    ACTION_NAME = "add_path"
    DSL_PARAM_ORDER = ("x", "y")
