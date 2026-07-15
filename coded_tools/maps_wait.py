# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
# Licensed under the Apache License, Version 2.0.
"""Typed wrapper for the MAPs ``wait`` action."""

from __future__ import annotations

from coded_tools.maps_action_base import MapsActionBase


class MapsWait(MapsActionBase):
    ACTION_NAME = "wait"
    DSL_PARAM_ORDER = ()
