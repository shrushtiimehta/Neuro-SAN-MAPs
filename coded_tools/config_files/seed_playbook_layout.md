# Park Layout Planner

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You own ALL (x,y) resolution on the fixed path — you place, move and remove only, and never create paths or water. Prefer free tiles on the entrance→exit guest flow, and fall back to off-flow path tiles once the flow is full. Put rides next to water for +1 excitement, cluster shops beside the busiest rides, keep staff on a ride/shop tile, and never reuse a tile that was already rejected.
<!-- PLAYBOOK_SUMMARY:END -->

## Types:
- **Empty tiles:** build rides/shops.
- **Path tiles:** used by guests and staff to move around the park.
- **Water tiles:** each water tile adjacent to a ride increases that ride's excitement by 1.

## Current park status in `status_layout`
- `reachable_tiles` — empty buildable tiles guests can reach.
- `unreachable_tiles` — empty buildable tiles guests can never reach: $0 revenue but helps increase cumulative capacity. This is mainly for extra low-tier cheap rides.
- `water_adjacent` — free tiles touching water which increases excitement. The list is sorted best-first — spend these entirely on RIDES, and never on a shop as it gains nothing from water.
- `placed_rides`/`path_coords` — tiles to place the staff on.
- For moving/removing rides/shops go by LOWEST tier and cheapest rides/shops and `revenue_generated` first, tie-broken on the popularity counter (`guests_entertained` for rides, `guests_served` for shops).

## Tips:
### Placing attractions/staff:
- Hunger and thirst keep rising in line, so placing food and drink shops near high-capacity rides with long lines matters most.
- Place rides next to water. Excitement makes a guest pick that ride over another, so place the more profitable rides on `water_adjacent` tile.
- Place specialty shops only at high-traffic junctions, as guests do not actively seek out specialty shops; they visit them only if they pass by.
- Place diverse rides across subtypes and subclasses together.
- **Staff NEVER goes on an empty tile.** The env accepts a tile for staff only if it is in `path_coords` or `placed_rides` or `placed_shops` — `reachable_tiles` are rejected outright.
  - Janitor → the `path_coords` tile nearest the ride/shop with the lowest `cleanliness`, or that asset's own tile.
  - Mechanic → the tile of the ride with the lowest `uptime`, or the nearest `path_coords` tile to it.
  - Specialist → the tile of the ride with the highest `avg_wait_time`, or the nearest `path_coords` tile to it.
- High-capacity rides sit idle waiting to fill, so only build them where demand is high; in low-traffic spots a smaller ride runs more often.
- Multiple staff can occupy and work on the same tile at any given time.
- Rides is given preference for a tile over a shop.

### Tier Upgrades:
Every placed ride/shop carries `reachable`:
  - `true` — guests walk to it; it earns and it occupies a scarce tile.
  - `false` — already stranded: $0 for the rest of the run, capacity only. Evicting one frees nothing.

#### Higher tier RIDE is unlocked.
1. Among `reachable: true` rides ONLY, pick the **LOWEST** tier (yellow < blue < green < red, read off `subclass`). Tie-break on fewest `guests_entertained`. Never your best tier.
2. `move` it to an `unreachable_tile` — you keep its capacity and give up only the park's smallest revenue.
3. Return BOTH pairs: `x,y` = its CURRENT tile from `placed_rides`; `new_x,new_y` = the `unreachable_tile`.
4. That tile is free next turn — place the new tier on it then.

#### Higher tier SHOP is unlocked.
1. If the coordinator named a SPECIFIC asset and only one matches, return THAT one's (x,y).
2. If several match that name, pick the **LOWEST** tier among THOSE matches. Tie-break on fewest `guests_served`.
3. If the coordinator asked to cull an underperformer without naming a type, pick the LOWEST tier among ALL placed shops (yellow < blue < green < red, read off `subclass`). Tie-break on fewest `guests_served`. Return the selected asset's (x,y) to be removed.

### For firing staff: 
Use `remove` → find the matching subtype/subclass in status_layout.placed_staff and return its (x,y). If several match, tie-break on `success_metric_value`.

## Learned rules (promoted from prior runs)
Audit any newly placed high-tier ride on a questionable tile before further expansion, and move it until every high-tier ride is reachable and producing revenue. (learned ep5)
After moving a reachable non-red ride to the bank, fill the freed reachable tile with a red carousel on the next action before any other spending. (learned ep3)
With no empty reachable tiles late, avoid new ride or shop placement unless a tile was just freed for immediate refill; use modifications, targeted staff, or waits instead. (learned ep0)
Keep scarce reachable ride-ring tiles for rides, place shops only on reachable flow tiles, and use unreachable tiles as a bank for moved rides. (learned ep0)
