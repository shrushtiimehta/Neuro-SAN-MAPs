# shops_manager - policy

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary (regenerated every episode)
Exercise t0_3: interleave shops with rides so cash flow funds expansion — ep0 had 0 shops. Place first shop by turn 5, reach num_shops>=2 by step 30, >=3 by step 50, >=4 by step 90. Keep cash never dropping below 0. Use shops to stabilize revenue between ride placements.
<!-- PLAYBOOK_SUMMARY:END -->

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
DIVERSIFICATION is very important: identical shops (same type and tier) give diminishing returns on park rating. ALWAYS vary the shop type and/or tier when options allow. When too few are unlocked to vary, don't place duplicates back-to-back — place them several steps apart.

- When a new tier appears in `available_entities`, replace the lowest-tier shop of that subtype via `remove`+`place` as soon as cash allows — don't just add the new tier alongside the old.
- `modify` only re-prices/restocks — CANNOT change tier. To upgrade, `remove`+`place` the new tier.
- Every consultation: check `placed_shops` for near-zero inventory first — a near-empty shop needs `modify` with larger `order_quantity`, same price.
- Specialty order: place yellow (Souvenir) early near high-traffic junctions; ATM only late-game when guest cash depletion is confirmed; Billboard only after food/ATM exists (earns $0 direct revenue).
- Sell shops that persistently run dry after 2+ restocks with no improvement, or are never visited across multiple consecutive days.

## How you move park_rating (status carries `park_rating`)
Shops affect rating by keeping guests happy and in service:
- **Happiness:** guests who get served leave happier (which raises rating); a guest turned away by an out-of-stock shop loses happiness.
- **Out of service:** a shop that runs DRY mid-day goes OUT OF SERVICE — that lowers happiness and rating. Staying stocked is a direct rating defence — keep `order_quantity` enough to last the day; fix near-empty shops first.

## Learned rules (promoted from prior runs)
Grow the drink/food shop base past the early plateau by mid-game so the repeated back-half modify loop has more high-yield targets to compound. (learned ep4)
When total ride_op_cost rises above shop_revenue, stop placing additional rides and add or modify food/drink shops until shop_revenue again exceeds ride_op_cost. (learned ep0)
Grow shop revenue by re-modifying high-velocity food and drink shops and avoid re-modifying specialty shops, which crash park_rating to its floor without compensating revenue. (learned ep1)

## Learned rules (promoted from prior runs)
When shop revenue already exceeds total ride operating cost, prioritize placing and modifying high-revenue shops over adding rides whose operating cost is high relative to their placement reward. (learned ep0)
