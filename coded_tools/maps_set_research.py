# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
# Licensed under the Apache License, Version 2.0.
"""Typed wrapper for the MAPs ``set_research`` action."""

from __future__ import annotations

from coded_tools.maps_action_base import MapsActionBase


class MapsSetResearch(MapsActionBase):
    ACTION_NAME = "set_research"
    DSL_PARAM_ORDER = ("research_speed", "research_topics")
