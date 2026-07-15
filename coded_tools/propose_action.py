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
"""
ProposeAction: agent-facing pre-step validator.

Replaces ActionDispatcher in the game-runner network's strategy_coordinator
tool list. Instead of stepping the MAPs env, this tool:
  1. validates that {park, action, args} is a syntactically-valid action,
  2. runs cheap deterministic checks against the latest observation,
  3. persists the proposal to a known state file so the external runner
     can read it after the agent's turn returns,
  4. returns a {proposed, validation} envelope to the agent so it can
     react if the validation fails (rare — the runner is the source of
     truth for retries).

The actual MAPs step is performed by the runner, not by this tool.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.action_dispatcher import ActionDispatcher
from coded_tools.finance_gate import _RIDES_ECONOMICS_PATH
from coded_tools.finance_gate import _SHOPS_ECONOMICS_PATH
from coded_tools.finance_gate import _STAFF_ECONOMICS_PATH
from coded_tools.finance_gate import _read_lookup_lines
from coded_tools.latest_observation import LatestObservation


# Where the runner picks up the latest proposal. The file is overwritten on
# every ProposeAction call. Override via env var for tests.
_PROPOSAL_PATH = os.environ.get(
    "MAPS_PROPOSED_ACTION_PATH",
    os.path.join(os.path.dirname(__file__), "state", "proposed_action.json"),
)

# Actions that don't cost the agent anything and don't need a state check.
_FREE_ACTIONS = {"wait", "survey_guests"}

_VALID_RESEARCH_SPEEDS = {"none", "slow", "medium", "fast"}

# Valid entity names for research_topics — rides + shops + staff subtypes.
_VALID_RESEARCH_TOPICS = {
    "carousel", "ferris_wheel", "roller_coaster",
    "drink", "food", "specialty",
    "janitor", "mechanic", "specialist",
}

# survey_guests: cost $500/guest, max 25 guests (from MAPs shared/config.json).
_SURVEY_GUESTS_COST_PER_GUEST = 500
_SURVEY_GUESTS_MAX = 25

# The only valid values for an action's `type` field (MAPs action_spec). A
# common mistake is using a subtype (e.g. 'janitor') as the type.
_VALID_TYPES = {"ride", "shop", "staff"}

# Parsed economics tables ({(domain, subtype, subclass): {field: value}}),
# cached at module level so the small tables are read once per process.
_RIDE_ECON_CACHE: dict | None = None
_SHOP_ECON_CACHE: dict | None = None
_STAFF_ECON_CACHE: dict | None = None


def _ride_economics() -> dict:
    global _RIDE_ECON_CACHE
    if _RIDE_ECON_CACHE is None:
        _RIDE_ECON_CACHE = _read_lookup_lines(_RIDES_ECONOMICS_PATH, "rides")
    return _RIDE_ECON_CACHE


def _shop_economics() -> dict:
    global _SHOP_ECON_CACHE
    if _SHOP_ECON_CACHE is None:
        _SHOP_ECON_CACHE = _read_lookup_lines(_SHOPS_ECONOMICS_PATH, "shops")
    return _SHOP_ECON_CACHE


def _staff_economics() -> dict:
    global _STAFF_ECON_CACHE
    if _STAFF_ECON_CACHE is None:
        _STAFF_ECON_CACHE = _read_lookup_lines(_STAFF_ECONOMICS_PATH, "staff")
    return _STAFF_ECON_CACHE


class ProposeAction(CodedTool):
    """Validate and persist a proposed MAPs action without stepping the env."""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        park = args.get("park", 0)
        action = args.get("action")
        action_args = args.get("args") or {}

        reasons: list[str] = []

        if not isinstance(action, str) or not action:
            reasons.append("action is required and must be a non-empty string")
        elif action not in ActionDispatcher.ACTION_TABLE:
            reasons.append(
                f"unknown action {action!r}; valid: {sorted(ActionDispatcher.ACTION_TABLE)}"
            )
        if not isinstance(action_args, dict):
            reasons.append(f"args must be an object/dict, got {type(action_args).__name__}")
            action_args = {}

        latest = self._read_latest_obs(park if isinstance(park, int) else 0)

        if action in {"place", "modify"}:
            atype = (action_args.get("type") or "").lower()
            # `type` must be ride/shop/staff. Using a subtype (e.g. 'janitor')
            # as the type is a common, always-failing mistake.
            if atype not in _VALID_TYPES:
                reasons.append(
                    f"{action} 'type' must be one of {sorted(_VALID_TYPES)} "
                    f"(got {action_args.get('type')!r}); janitor/mechanic/specialist "
                    f"are subtypes of type='staff', and ride/shop subtypes go under "
                    f"type='ride'/'shop'."
                )

            # modify is a partial update: it locates the asset by type+(x,y),
            # then carries forward the fields the agent didn't restate (subtype,
            # subclass, price, and order_quantity for shops). So a modify only
            # needs type+x+y plus whatever it is changing — the env's "missing
            # arg" / price=None rejections are filled in here instead.
            if action == "modify" and atype in _VALID_TYPES:
                if action_args.get("x") is None or action_args.get("y") is None:
                    reasons.append("modify needs integer x and y to locate the asset")
                elif latest and self._matched_asset(action_args, latest) is None:
                    reasons.append(
                        f"no {atype} found at ({action_args.get('x')},"
                        f"{action_args.get('y')}) to modify (check placed_{atype}s in ParkStatus)"
                    )
                else:
                    self._carry_forward_modify(action_args, latest)

            # Price is NEVER taken from the agent: overwrite it deterministically
            # from the economics files (max cap for ride/shop, salary for staff).
            # This is the authoritative chokepoint — the runner steps the env from
            # the proposal this tool persists — so a wrong agent price (e.g. the
            # food cap 5 leaking onto a drink shop capped at 3) can't reach the env.
            self._force_econ_price(action_args)

            price_ok, price_reason = self._check_price_cap(action_args, latest)
            if not price_ok:
                reasons.append(price_reason)
            # Per-subclass price cap from the economics table (max_ticket_price
            # for rides, max_item_price for shops) — not present in the obs.
            cap_ok, cap_reason = self._check_price_cap_econ(action_args)
            if not cap_ok:
                reasons.append(cap_reason)
            # All env-required fields present (after modify carry-forward).
            req_ok, req_reason = self._check_required_fields(action, action_args)
            if not req_ok:
                reasons.append(req_reason)

        if action == "place":
            bounds_ok, bounds_reason = self._check_place_bounds(action_args, latest)
            if not bounds_ok:
                reasons.append(bounds_reason)
            avail_ok, avail_reason = self._check_subclass_available(action_args, latest)
            if not avail_ok:
                reasons.append(avail_reason)
            tile_ok, tile_reason = self._check_placement_tile(action_args, latest)
            if not tile_ok:
                reasons.append(tile_reason)

        if action == "remove":
            rem_ok, rem_reason = self._check_remove_coords(action_args, latest)
            if not rem_ok:
                reasons.append(rem_reason)

        if action == "move":
            move_ok, move_reason = self._check_move_fields(action_args, latest)
            if not move_ok:
                reasons.append(move_reason)

        if action == "set_research":
            sr_ok, sr_reason = self._check_set_research_fields(action_args)
            if not sr_ok:
                reasons.append(sr_reason)

        if action == "survey_guests":
            sg_ok, sg_reason = self._check_survey_guests_fields(action_args)
            if not sg_ok:
                reasons.append(sg_reason)

        if action and action not in _FREE_ACTIONS and reasons == []:
            cash_ok, cash_reason = self._check_cash(action, action_args, latest)
            if not cash_ok:
                reasons.append(cash_reason)

        validation = {"ok": not reasons, "reasons": reasons}
        proposed = {"park": park, "action": action, "args": action_args}
        envelope = {
            "proposed": proposed,
            "validation": validation,
            "wall_time": time.time(),
        }

        try:
            os.makedirs(os.path.dirname(_PROPOSAL_PATH) or ".", exist_ok=True)
            with open(_PROPOSAL_PATH, "w", encoding="utf-8") as fh:
                json.dump(envelope, fh)
        except OSError as err:
            envelope["persist_error"] = f"could not write proposal file: {err}"

        return envelope

    def _read_latest_obs(self, park: int) -> dict[str, Any]:
        """Best-effort: read the latest observation for the given park slot.

        Returns the inner observation dict on success, or {} if the cache is
        absent / unreadable / structured unexpectedly. Validation downgrades
        gracefully when no observation is available (e.g., turn 0 before any
        ActionDispatcher call).
        """
        path = LatestObservation.DEFAULT_PATH
        if not os.path.exists(path):
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                cache = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(cache, dict):
            return {}
        entries = cache.get(f"park_{park}") or cache.get(str(park)) or []
        if not entries:
            return {}
        last = entries[-1] if isinstance(entries, list) else entries
        if not isinstance(last, dict):
            return {}
        obs = last.get("observation") or last
        return obs if isinstance(obs, dict) else {}

    # modify/place 'price' maps to a type-specific field on the asset; this is
    # also where the asset's current price lives in the observation.
    _PRICE_SECTION: ClassVar[dict[str, tuple[str, str, str]]] = {
        # type -> (obs section key, list key, price field on each item)
        "ride":  ("rides",  "ride_list",  "ticket_price"),
        "shop":  ("shops",  "shop_list",  "item_price"),
        "staff": ("staff",  "staff_list", "salary"),
    }

    def _matched_asset(self, action_args: dict, obs: dict) -> dict | None:
        """Return the asset dict at type+(x,y) from the observation, or None."""
        mapping = self._PRICE_SECTION.get((action_args.get("type") or "").lower())
        if not mapping:
            return None
        section_key, list_key, _price_field = mapping
        try:
            tx, ty = int(action_args.get("x")), int(action_args.get("y"))
        except (TypeError, ValueError):
            return None
        section = obs.get(section_key)
        items = section.get(list_key) if isinstance(section, dict) else None
        for item in items or []:
            if isinstance(item, dict) and item.get("x") == tx and item.get("y") == ty:
                return item
        return None

    def _carry_forward_modify(self, action_args: dict, obs: dict) -> None:
        """Fill a modify's omitted asset fields from the matched asset.

        A modify only changes price / order_quantity; subtype, subclass and the
        unchanged price all describe the existing asset and can be read back
        from the observation. Only fills fields the agent left None/empty.
        """
        asset = self._matched_asset(action_args, obs)
        if not asset:
            return
        mapping = self._PRICE_SECTION.get((action_args.get("type") or "").lower())
        price_field = mapping[2] if mapping else None
        for key in ("subtype", "subclass"):
            if action_args.get(key) in (None, "") and asset.get(key) is not None:
                action_args[key] = asset.get(key)
        if action_args.get("price") is None and price_field:
            value = asset.get(price_field)
            if isinstance(value, int) and not isinstance(value, bool):
                action_args["price"] = value
        if (action_args.get("type") or "").lower() == "shop" and action_args.get("order_quantity") is None:
            oq = asset.get("order_quantity")
            if isinstance(oq, int) and not isinstance(oq, bool):
                action_args["order_quantity"] = oq

    # Where each entity type's authoritative price lives in the economics
    # tables. Rides/shops are capped (we always charge the cap); staff "price"
    # is the fixed salary.
    _ECON_PRICE_FIELD: ClassVar[dict[str, tuple[str, str]]] = {
        # type -> (economics domain, field name)
        "ride":  ("rides", "max_ticket_price"),
        "shop":  ("shops", "max_item_price"),
        "staff": ("staff", "salary"),
    }

    def _force_econ_price(self, action_args: dict) -> None:
        """Authoritatively set ``price`` from the economics files; the agent's
        value is always discarded.

        Rides/shops use the per-subclass max cap (max_ticket_price /
        max_item_price) — the network design always charges the max and the env
        rejects anything above it. Staff use their fixed salary. Mutates
        ``action_args`` in place so the persisted proposal (which the runner
        steps the env from) carries the correct price.

        Leaves ``price`` untouched only when the type/subtype/subclass can't be
        resolved to an economics row (e.g. a modify whose asset wasn't found, or
        a typo'd subtype) — those cases are rejected by the other checks.
        """
        atype = (action_args.get("type") or "").lower()
        subtype = (action_args.get("subtype") or "").lower()
        subclass = (action_args.get("subclass") or "").lower()
        mapping = self._ECON_PRICE_FIELD.get(atype)
        if not mapping or not subtype or not subclass:
            return
        domain, field = mapping
        econ = {"rides": _ride_economics, "shops": _shop_economics, "staff": _staff_economics}[domain]()
        entry = econ.get((domain, subtype, subclass))
        value = entry.get(field) if entry else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            action_args["price"] = int(value)

    def _check_price_cap(self, action_args: dict, obs: dict) -> tuple[bool, str]:
        """Validate that price, when present, is an integer. Presence itself is
        enforced by _check_required_fields so the messages don't double up."""
        price = action_args.get("price")
        if price is None:
            return True, ""
        try:
            price = int(price) if not isinstance(price, bool) else None
        except (TypeError, ValueError):
            return False, f"price must be an integer, got {price!r}"
        if price is None:
            return False, "price must be an integer, not a boolean"
        return True, ""

    def _check_price_cap_econ(self, action_args: dict) -> tuple[bool, str]:
        """Reject a price above the subclass's economics max.

        The env enforces a per-subclass cap — max_ticket_price for rides,
        max_item_price for shops — that is NOT in the observation, so we read
        it from the economics tables (the same the agent consults). Staff have
        no such cap.
        """
        atype = (action_args.get("type") or "").lower()
        if atype == "ride":
            econ, max_field, domain, label = _ride_economics(), "max_ticket_price", "rides", "ticket price"
        elif atype == "shop":
            econ, max_field, domain, label = _shop_economics(), "max_item_price", "shops", "item price"
        else:
            return True, ""
        subtype = (action_args.get("subtype") or "").lower()
        subclass = (action_args.get("subclass") or "").lower()
        price = action_args.get("price")
        if not subtype or not subclass or price is None:
            return True, ""  # presence/type handled elsewhere
        try:
            price = int(price)
        except (TypeError, ValueError):
            return True, ""
        entry = econ.get((domain, subtype, subclass))
        cap = entry.get(max_field) if entry else None
        if isinstance(cap, (int, float)) and price > cap:
            return False, (
                f"{label} {price} exceeds {max_field} {cap} for "
                f"{subtype} {subclass}; set it to {cap} or lower"
            )
        return True, ""

    def _check_required_fields(self, action: str, action_args: dict) -> tuple[bool, str]:
        """Ensure every env-required field is present for place/modify.

        Only place/modify are checked (the actions that were failing). For
        modify this runs AFTER carry-forward, so an asset that was located has
        its fields filled; a still-missing field means the agent gave too
        little to act on. order_quantity is required for shops only.
        """
        if action == "place":
            required = ["type", "subtype", "subclass", "x", "y", "price"]
        elif action == "modify":
            required = ["type", "subtype", "subclass", "x", "y", "price"]
        else:
            return True, ""
        if (action_args.get("type") or "").lower() == "shop":
            required.append("order_quantity")
        missing = [k for k in required if action_args.get(k) in (None, "")]
        if missing:
            return False, (
                f"{action} is missing required field(s) {missing}; provide them "
                f"(rides/shops/staff use type=ride/shop/staff, and shops need "
                f"order_quantity)"
            )
        return True, ""

    def _check_placement_tile(self, action_args: dict, obs: dict) -> tuple[bool, str]:
        """Reject a ride/shop placement on a tile that is not buildable.

        valid_placement_coords (surfaced to the agent as `free_tiles` in
        ParkStatus) lists the empty tiles adjacent to the reachable path — i.e.
        exactly where rides/shops may go. Enforcing it pre-empts the env's
        "must be adjacent to a path" and "tile already contains a ride"
        rejections. Staff have a different rule (on a path / in an attraction),
        so they are left to the env. Skipped when the list is unavailable.
        """
        if (action_args.get("type") or "").lower() not in ("ride", "shop"):
            return True, ""
        coords = obs.get("valid_placement_coords")
        if not isinstance(coords, list) or not coords:
            return True, ""  # no signal available; let the env decide
        try:
            x, y = int(action_args.get("x")), int(action_args.get("y"))
        except (TypeError, ValueError):
            return True, ""  # x/y validity handled by _check_place_bounds
        valid = {(c[0], c[1]) for c in coords if isinstance(c, (list, tuple)) and len(c) >= 2}
        if (x, y) not in valid:
            return False, (
                f"({x},{y}) is not a buildable tile for a {action_args.get('type')}; "
                f"choose one of free_tiles from ParkStatus (empty tiles next to the path)."
            )
        return True, ""

    def _check_subclass_available(self, action_args: dict, obs: dict) -> tuple[bool, str]:
        """Reject placing a subclass that research has not unlocked yet.

        The observation's ``available_entities`` maps each subtype to the
        subclasses currently buildable (e.g. ``{"carousel": ["yellow"]}``).
        Catches "X has not been researched yet" env rejections before dispatch.
        """
        subtype = action_args.get("subtype")
        subclass = action_args.get("subclass")
        if not subtype or not subclass:
            return True, ""
        available = obs.get("available_entities")
        if not isinstance(available, dict):
            return True, ""  # no info; let the env decide
        allowed = available.get(subtype)
        if allowed is None:
            return True, ""  # unknown subtype; let the env decide
        if subclass not in allowed:
            return False, (
                f"subclass {subclass!r} is not available for {subtype!r} yet "
                f"(available now: {allowed}). Set research to unlock higher tiers, "
                f"or place an available subclass."
            )
        return True, ""

    def _check_place_bounds(self, action_args: dict, obs: dict) -> tuple[bool, str]:
        x, y = action_args.get("x"), action_args.get("y")
        try:
            x = int(x); y = int(y)
        except (TypeError, ValueError):
            return False, f"place needs integer x,y; got x={x!r}, y={y!r}"
        bounds = obs.get("park_bounds") or obs.get("bounds") or {}
        if bounds:
            w, h = bounds.get("width"), bounds.get("height")
            if isinstance(w, int) and not (0 <= x < w):
                return False, f"x={x} out of park width {w}"
            if isinstance(h, int) and not (0 <= y < h):
                return False, f"y={y} out of park height {h}"
        if x < 0 or y < 0:
            return False, f"x,y must be non-negative; got x={x}, y={y}"
        return True, ""

    def _check_remove_coords(self, action_args: dict, obs: dict) -> tuple[bool, str]:
        """Reject a remove that omits integer x,y — the env always requires them."""
        x, y = action_args.get("x"), action_args.get("y")
        try:
            ix, iy = int(x), int(y)
        except (TypeError, ValueError):
            return False, (
                f"remove requires integer x,y to locate the asset; got x={x!r}, y={y!r}. "
                f"Look up the target's (x,y) from placed_rides/placed_shops/placed_staff "
                f"in ParkStatus and pass them explicitly."
            )
        if obs:
            atype = (action_args.get("type") or "").lower()
            mapping = self._PRICE_SECTION.get(atype)
            if mapping:
                section_key, list_key, _ = mapping
                section = obs.get(section_key)
                items = section.get(list_key) if isinstance(section, dict) else None
                if items is not None:
                    found = any(
                        isinstance(item, dict) and item.get("x") == ix and item.get("y") == iy
                        for item in items
                    )
                    if not found:
                        return False, (
                            f"no {atype} found at ({ix},{iy}) to remove; "
                            f"check placed_{atype}s in ParkStatus for valid coords."
                        )
        return True, ""

    def _check_move_fields(self, action_args: dict, obs: dict) -> tuple[bool, str]:
        """Validate move has type + integer current coords (asset exists) + integer destination."""
        atype = (action_args.get("type") or "").lower()
        if atype not in _VALID_TYPES:
            return False, (
                f"move 'type' must be one of {sorted(_VALID_TYPES)}; got {action_args.get('type')!r}"
            )
        x, y = action_args.get("x"), action_args.get("y")
        try:
            ix, iy = int(x), int(y)
        except (TypeError, ValueError):
            return False, f"move requires integer x,y for the current position; got x={x!r}, y={y!r}"
        new_x, new_y = action_args.get("new_x"), action_args.get("new_y")
        try:
            inx, iny = int(new_x), int(new_y)
        except (TypeError, ValueError):
            return False, (
                f"move requires integer new_x,new_y for the destination; "
                f"got new_x={new_x!r}, new_y={new_y!r}"
            )
        if obs:
            mapping = self._PRICE_SECTION.get(atype)
            if mapping:
                section_key, list_key, _ = mapping
                section = obs.get(section_key)
                items = section.get(list_key) if isinstance(section, dict) else None
                if items is not None:
                    found = any(
                        isinstance(item, dict) and item.get("x") == ix and item.get("y") == iy
                        for item in items
                    )
                    if not found:
                        return False, (
                            f"no {atype} found at ({ix},{iy}) to move; "
                            f"check placed_{atype}s in ParkStatus for valid current coords."
                        )
            if atype in ("ride", "shop"):
                # Destination must be adjacent to a path (valid_placement_coords).
                coords = obs.get("valid_placement_coords")
                if isinstance(coords, list) and coords:
                    valid = {(c[0], c[1]) for c in coords if isinstance(c, (list, tuple)) and len(c) >= 2}
                    if (inx, iny) not in valid:
                        return False, (
                            f"({inx},{iny}) is not a buildable destination for a {atype}; "
                            f"choose a tile from free_tiles in ParkStatus."
                        )
            elif atype == "staff":
                # Staff must land on a path or attraction tile, not empty/water.
                path_coords = obs.get("path_coords")
                if isinstance(path_coords, list) and path_coords:
                    path_set = {(c[0], c[1]) for c in path_coords if isinstance(c, (list, tuple)) and len(c) >= 2}
                    attraction_coords = {
                        (item["x"], item["y"])
                        for section_key in ("rides", "shops", "staff")
                        for list_key in (f"{section_key.rstrip('s')}_list",)
                        for item in (obs.get(section_key) or {}).get(list_key, [])
                        if isinstance(item, dict) and "x" in item and "y" in item
                    }
                    valid = path_set | attraction_coords
                    if valid and (inx, iny) not in valid:
                        return False, (
                            f"({inx},{iny}) is not a valid destination for staff; "
                            "staff must move to a path tile or inside an existing attraction."
                        )
        return True, ""

    def _check_set_research_fields(self, action_args: dict) -> tuple[bool, str]:
        """Validate set_research speed and topic entity names."""
        speed = (action_args.get("research_speed") or "none").lower().strip()
        if speed not in _VALID_RESEARCH_SPEEDS:
            return False, (
                f"research_speed must be one of {sorted(_VALID_RESEARCH_SPEEDS)}; got {speed!r}"
            )
        topics = action_args.get("research_topics")
        if topics is not None:
            if not isinstance(topics, list):
                return False, "research_topics must be an array/list"
            invalid = [t for t in topics if t not in _VALID_RESEARCH_TOPICS]
            if invalid:
                return False, (
                    f"invalid research_topics {invalid}; must be from "
                    f"{sorted(_VALID_RESEARCH_TOPICS)}"
                )
        return True, ""

    def _check_survey_guests_fields(self, action_args: dict) -> tuple[bool, str]:
        """Validate num_guests is an integer in [1, 25]."""
        raw = action_args.get("num_guests")
        try:
            n = int(raw)
        except (TypeError, ValueError):
            return False, (
                f"survey_guests requires integer num_guests (1–{_SURVEY_GUESTS_MAX}); got {raw!r}"
            )
        if n < 1:
            return False, (
                f"num_guests must be at least 1; got {n}"
            )
        if n > _SURVEY_GUESTS_MAX:
            return False, (
                f"num_guests must be <= {_SURVEY_GUESTS_MAX} (max_guests_to_survey); got {n}"
            )
        return True, ""

    def _check_cash(self, action: str, action_args: dict, obs: dict) -> tuple[bool, str]:
        cash = obs.get("cash")
        if not isinstance(cash, (int, float)):
            return True, ""  # no cash signal available; let the env decide
        if cash <= 0 and action != "remove":
            return False, f"cash is non-positive ({cash}); only 'remove' or free actions are safe"
        return True, ""
