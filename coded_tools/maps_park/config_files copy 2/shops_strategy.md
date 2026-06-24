# shops_manager - policy

Every proposal you send out must have a clear break-even rationale. Prefer long-term compounding investments over conservative short-term plays. Idle steps are permanently lost value.

## Shop mechanics
1. **order_quantity** — at day start, inventory is bought at `item_cost`; if cash is insufficient, partial stocking occurs. Unsold items spoil end-of-day. Update via `modify`.
2. **item_cost** — per-unit cost paid by you.
3. **item_price** — per-unit price paid by guests; always set to `max_item_price`.
If a shop runs out mid-day it goes OUT OF SERVICE — turns guests away, hurts happiness and rating.

## Shop types (all have 4 tiers: yellow < blue < green < red)
- **Drink** (higher tier = more thirst reduction + higher price cap): quenches thirst. Green tier also boosts happiness; red tier makes guest move at 2× speed for several steps after purchase.
- **Food** (higher tier = more hunger reduction + higher price cap): satisfies hunger. Green tier also quenches thirst; red tier gives an extra happiness boost.
- **Specialty** (subclass sets the function — place with `subtype='specialty', subclass=<colour>`):
  - yellow = Souvenir: boosts happiness; boost halves with each souvenir a guest buys.
  - blue = Info Booth: guests only target attractions matching their preference that they can afford.
  - green = ATM: lets guests withdraw cash; amount withdrawn halves on each use down to a minimum.
  - red = Billboard: raises guest hunger/thirst/happiness and resets shop visit counts; steers low-cash guests toward the nearest ATM.

- Every consultation: check `placed_shops` for near-zero inventory first — a near-empty shop needs `modify` with larger `order_quantity`, same price.
- Specialty order: yellow (Souvenir) early near high-traffic junctions; ATM only late-game when guest cash depletion is confirmed; Billboard only after food/ATM exists (earns $0 direct revenue).
- `modify` only re-prices/restocks — CANNOT change tier. To upgrade, `remove`+`place` the new tier.
- On tier unlock: replace a lower-tier shop via `remove`+`place` as soon as cash allows.
- Sell shops that persistently run dry after 2+ restocks with no improvement, or are never visited across multiple consecutive days.

## Learned rules (promoted from prior runs)
- Prefer food over drink for shop modifies once both exist: when choosing which shop to modify, modify the food shop instead of repeating a drink modify — food modifies have returned the highest per-turn shop rewards this run; rotate back to drink only after a food modify.
- Early modify engine: once a janitor has restored min_cleanliness >= 0.80 with at least 2 shops placed, prioritize modify on the existing drink/food shops at the same price over new placements; consecutive same-shop modifies in this early window (step < 30) deliver large rising per-turn rewards.
- No back-to-back specialty modify: do not modify the same specialty shop on two consecutive turns; after one specialty modify, switch to a different shop subtype (drink/food) or wait before re-modifying specialty.
