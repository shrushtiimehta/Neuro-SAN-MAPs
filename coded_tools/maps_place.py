# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
# Licensed under the Apache License, Version 2.0.
"""Typed wrapper for the MAPs ``place`` action."""

from __future__ import annotations

from coded_tools.maps_action_base import MapsActionBase


class MapsPlace(MapsActionBase):
    ACTION_NAME = "place"
    DSL_PARAM_ORDER = ("x", "y", "type", "subtype", "subclass", "price", "order_quantity")
    OPTIONAL_PARAMS = {"order_quantity"}
