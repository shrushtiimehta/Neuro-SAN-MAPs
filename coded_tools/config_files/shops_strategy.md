# Shop Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which shops to place, restock (modify order_quantity), or sell — drink/food/specialty across four tiers (never coordinates). Shops drive recurring revenue and guest happiness; the golden rule is never let a shop run dry, since out-of-service crashes happiness and park_rating.
<!-- PLAYBOOK_SUMMARY:END -->

Shops are necessary to adequately cater to guest needs, and provide **additional value to a park**.

## Types of shops:
- **Drink:** quenches guests’ thirst.
- **Food:** satisfies guests’ hunger.
- **Specialty:** provides unique services based on subclass:
  - Yellow (Souvenir Shops): boost guest happiness.
  - Blue (Info Booths): inform guests about attractions and their prices. It removes the rejection penalty.
  - Green (ATMs): allow guests to withdraw additional funds. Guests arrive with ~$150, so revenue past that ceiling can come from an ATM. 
  - Red (Billboards): encourage guests to seek food and ATMs (useful when food shops and an ATM already exist to absorb the extra demand). Earns zero revenue but resets visit counts, drawing more guests.

## Key attributes:
- **Order quantity:** quantity of inventory.
  - At the start of the day, shops are stocked to order quantity at item cost.
  - If funds are insufficient, partial stocking will occur.
  - If a shop runs out of inventory during the day, it will go out of service, turning away guests and lowering their happiness and your park rating.
  - Order quantity can be increased using the *modify* action, but treat *modify* as a LAST RESORT: it costs a whole step and adds no capacity and no excitement, where a placement earns for the rest of the episode. Spend one only on a shop actually going dry early in the day (low uptime) — never to fine-tune a shop already in service — and set order_quantity right the first time so you never have to come back to it.
- **Item cost/price:** the cost of purchasing/selling one unit of inventory.

## Park current status (not set by you)
- **inventory** — units left unsold.
- **profit** — sales income minus stocking cost for that shop.
- **uptime** — fraction of the day the shop stayed in service (not dry).
- **next_unlock** — the next tier due and which subtype unlocks next, e.g. `"next_unlock": {"tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. `days` is the ETA for the first listed unlock. Absent = research off.

## Tips:
- **Guests leave** when money, energy, hunger, thirst, or happiness runs critical. Hunger/thirst rise and happiness falls over time, so food/drink shops and rides are what keep guests in the park spending. Keep this in mind while building shops.
- **Thirst in guests builds ~1.5× faster than hunger.**
- When research unlocks a higher tier (yellow < blue < green < red; see `available_entities`) and cash allows, place it in priority.
- **Tier-upgrade swap — reachable tiles are scarce, so keep the shop count small and grow it by UPGRADING the shops you already have, not by adding more.** A higher tier unlocked? Swap ONE shop, over two turns:
  1. `remove` your lowest-tier shop. Tie-break on least `profit`. Prefer one whose subtype just unlocked.
  2. `place` the new tier on the tile it vacated. Never on an unreachable tile: revenue is always $0.
- Building multiple shops of the same kind (i.e., identical subtype and subclass) yields diminishing returns for your park rating. Whenever possible, **DIVERSIFY** your shops across subtypes and subclasses for a higher overall rating.
- A shop sells back for only 66% of its build cost, so swap only for a genuine tier upgrade.

## Learned rules (promoted from prior runs)
