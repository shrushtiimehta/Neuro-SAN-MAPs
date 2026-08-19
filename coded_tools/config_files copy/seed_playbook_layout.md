# Park Layout Planner

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You own ALL (x,y) resolution on the fixed path — you place, move and remove only, and never create paths or water. Prefer free tiles on the entrance→exit guest flow, and fall back to off-flow path tiles once the flow is full. Put rides next to water for +1 excitement, cluster shops beside the busiest rides, keep staff on a ride/shop tile, and never reuse a tile that was already rejected.
<!-- PLAYBOOK_SUMMARY:END -->

## Types:
- **Empty tiles:** build rides/shops.
- **Path tiles:** used by guests to move around the park.
- **Water tiles:** each water tile adjacent to a ride increases that ride's excitement by 1, and it STACKS — a ride touching two water tiles is +2 and so on.

## Status Variables:
- `reachable_tiles` — empty tiles guests can reach.
- `water_adjacent` — free tiles touching water, as `{x, y, water}`. `water` is the excitement bonus and it STACKS: a tile between two water tiles is +2. The list is sorted best-first — spend these entirely on RIDES, and never on a shop or staff, which gain nothing from water.
- `unreachable_tiles` — buildable tiles guests can never walk to: $0 revenue but helps increase cumulative capacity. Site here ONLY as the DESTINATION of an eviction `move` that frees a reachable tile for a higher tier. Don't place shops or new rides here.
- `placed_rides` and `path_coords` — tiles to place the staff on.
- every placed ride/shop carries `subclass` (its tier), `reachable` and `cleanliness`. Rides add `capacity`, `excitement`, `guests_entertained`, `uptime` and `avg_wait_time`; shops add `guests_served` — shops have no capacity or excitement at all. Evictions go by LOWEST tier first, tie-broken on the popularity counter (`guests_entertained` for rides, `guests_served` for shops); the rest rank which asset is worth siting near.

## Tips:
### Placing attractions/staff:
- Hunger and thirst keep rising in line, so placing food and drink shops near high-capacity rides with long lines matters most.
- Place rides next to water: +1 excitement per adjacent water tile, stacking. Excitement is what makes a guest pick that ride over another, so take the highest-`water` tile in `water_adjacent` before any plain free tile.
- Guests favor kinds of attractions they haven't visited before and whatever is nearby, but never visit the same attraction twice in a row.
- Place specialty shops only at high-traffic junctions, as guests do not actively seek out specialty shops; they visit them only if they pass by.
- Place diverse rides across subtypes and subclasses together.
- **Staff NEVER go on an empty tile.** The env accepts a staff tile only if it is a path tile or already holds a ride/shop — an empty tile is rejected outright and the turn is lost. So staff coordinates come from `path_coords`, or from the (x,y) of an entry in `placed_rides`/`placed_shops`. Never from `reachable_tiles`.
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

#### `reachable_tiles` is empty AND a higher tier RIDE is unlocked.
1. Among `reachable: true` rides ONLY, pick the LOWEST tier (yellow < blue < green < red, read off `subclass`). Tie-break on fewest `guests_entertained`. Never your best tier.
2. `move` it to an `unreachable_tile` — you keep its capacity and give up only the park's smallest revenue.
3. Return BOTH pairs: `x,y` = its CURRENT tile from `placed_rides`; `new_x,new_y` = the `unreachable_tile`.
4. That tile is free next turn — place the new tier on it then.

#### `reachable_tiles` is empty AND a higher tier SHOP is unlocked.
1. If the coordinator named a SPECIFIC asset (e.g. a tier-upgrade swap: "remove the yellow drink shop") and only one matches, return THAT one's (x,y).
2. If several match that name, pick the LOWEST tier among THOSE matches. Tie-break on fewest `guests_served`.
3. If the coordinator asked to cull an underperformer without naming a type, pick the LOWEST tier among ALL placed shops (yellow < blue < green < red, read off `subclass`). Tie-break on fewest `guests_served`. Return the selected asset's (x,y) to be removed.

### For firing staff: 
Use `remove` → find the matching subtype/subclass in status_layout.placed_staff and return its (x,y). If several match, tie-break on `success_metric_value`.

## Learned rules (promoted from prior runs)
Pre-clear premium ride target tiles only when the cleared tile will be filled immediately or on the unlock turn, so premium conversion avoids occupied-tile rejections without leaving revenue tiles idle. (learned ep3)
Late in a crowded build, only place rides on freshly vacated or verified empty tiles; if no slot is clear, repair uptime or restock shops instead of blind placement. (learned ep2)
