# Shop Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which drink, food, and specialty shops to place, restock (`modify`), or sell across four tiers, but you never choose coordinates. Shops generate recurring revenue and improve guest happiness. The golden rule is never to let a shop run dry because an out-of-service shop reduces happiness and `park_rating`.
<!-- PLAYBOOK_SUMMARY:END -->

**Guests leave** when money, energy, hunger, thirst, or happiness becomes critical, and shops address all five needs. A guest who leaves early takes all their remaining spending money with them. Monitor `avg_money_spent` and `avg_time_in_park` in `status_shops`. Each guest starts with a randomly sampled amount of money with a mean of $150 and a standard deviation of $25. Aim to increase guest spending.
Review `shops_economics` to select the shop that addresses the failing need identified through the guest metrics in `status_shops`.
Higher-tier shops address more needs and do so more effectively. Prefer placing higher-tier shops.

## Types of shops:
- **Drink:** quenches thirst. Thirst builds approximately 1.5 times faster than hunger.
- **Food:** satisfies guests' hunger.
- **Specialty:** provides a unique service for each subclass; see `shops_economics`.

## Key attributes:
- **Item cost:** the amount paid per unit.
- **Order quantity:** the number of units restocked each morning at `item_cost`. A shop that runs out of inventory goes out of service and lowers park rating, so increase its order quantity when necessary. Monitor each shop's uptime.
- **Item price:** fixed and listed in `shops_economics`.

## Current park status is in `status_shops`:
- **inventory** — units left unsold.
- **guests_served** — the number of guests served, which indicates popularity.
- **reachable** — `false` means guests can never reach the shop, so it earns $0. Move it to a slot in `reachable_tiles`; do not `modify` it.

## `Modify` to set `order_quantity`:
Changing `order_quantity` costs an entire step, so do so only when a shop's metrics justify it. Increase `order_quantity` when `uptime` is well below 1 or when the shop is `out_of_service` because it ran dry. Decrease `order_quantity` when too much `inventory` remains at closing.

## Tier upgrades:
- Place higher-tier shops **as soon as** research unlocks them and cash allows (yellow < blue < green < red). In `status_shops`, check `available_entities` for unlocked tiers and `next_unlock` to prepare for upcoming unlocks. Higher tiers pay back far more and offer distinct benefits; review `economics_shops` and exploit those benefits.
- **HOW TO PLACE HIGHER TIERS?**
  1. `remove` your lowest-tier shop of the same subtype. Break ties by choosing the shop with the fewest `guests_served`.
  2. `place` the higher-tier shop on the vacated tile. Never place a shop on an unreachable tile because it will always earn $0.
- Otherwise, avoid `remove`. Swap shops only for a genuine tier upgrade, and do not place a shop unless it is needed.

## Learned rules (promoted from prior runs)
After step 80, restock any food, drink, or specialty shop that is approaching stockout at its current legal price with enough inventory to finish the episode while preserving the next red-carousel reserve. (learned ep9)
After an uptime emergency is patched, replace remaining legacy drink shops with the best unlocked drink at a legal price and enough stock to restore shop count within one turn before other shop restocks. (learned ep7)
Place reachable yellow drink, food, and specialty shops early for needs coverage, then add specialty support once high-ticket carousel traffic is earning. (learned ep0)
