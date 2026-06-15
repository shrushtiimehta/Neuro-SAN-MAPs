# shops_manager - policy

- **Timing:** do NOT place a new shop until ≥1 ride is operational and drawing guests (shops earn nothing without guests).
- **Restock priority:** check `status.placed_shops` FIRST and EVERY consultation for shops at or near zero inventory. A near-empty shop requires a `modify` with a larger `order_quantity` and the SAME price (do not change price on a restock-only modify). Classify and report any such shop as TOP PRIORITY over all new placements - never skip this check.
- **Drink before food:** guests get thirsty faster than hungry - read `thirst_build_rate` vs `hunger_build_rate` from `state_read(name='world_constants')` to confirm, then recommend drink first.
- **Specialty shop reasoning:**
  - Billboards (max_item_price=0) generate no direct revenue; recommend only after food / ATM infrastructure exists to channel guests toward.
  - ATMs are expensive (high building_cost); recommend only late game when guest money depletion is confirmed by surveys.
  - Souvenir shops (yellow specialty) are cheap to build with the highest item margin; good early placement near high-traffic path intersections.
- **Order quantity sizing:** size `order_quantity` to 3× the highest single-turn consumption over the last 5 turns, floor 15 units, capped so it still fits within available cash after the action (leave a $100 buffer). Also restock all drink/food shops immediately after any ride placement, regardless of current stock (new capacity raises guest flow; a stockout puts a shop out of service).
- **Order quantity null fallback:** before dispatching any shop `modify`, assert `order_quantity` is a positive integer ≥ 1. If it is None/null, substitute `max(30, last_turn_units_sold × 3)`, keep the current price unchanged, and never skip the restock.
- **New tier/colour = `place`, NEVER `modify`:** `modify` only re-prices/restocks the shop already on a tile - it CANNOT change its tier. To deploy a higher-tier shop you MUST `place` a new one (or `remove`+`place`); pricing then follows the normal placement rules.
- **Sell rules:** recommend selling shops that persistently run dry (restocked twice or more with no sales improvement) or are never visited across multiple consecutive days.

## Learned rules (promoted from prior runs)
- Prefer food over drink for shop modifies once both exist: when choosing which shop to modify, modify the food shop instead of repeating a drink modify — food modifies have returned the highest per-turn shop rewards this run; rotate back to drink only after a food modify. (learned ep0)
- Early modify engine: once a janitor has restored min_cleanliness >= 0.80 with at least 2 shops placed, prioritize modify on the existing drink/food shops at the same price over new placements; consecutive same-shop modifies in this early window (step < 30) deliver large rising per-turn rewards. (learned ep0)
- No back-to-back specialty modify: do not modify the same specialty shop on two consecutive turns; after one specialty modify, switch to a different shop subtype (drink/food) or wait before re-modifying specialty. (learned ep0)
