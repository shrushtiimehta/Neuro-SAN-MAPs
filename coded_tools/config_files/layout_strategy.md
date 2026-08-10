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
- `free_tiles` — empty tiles adjacent to the path that connects the entrance to the exit.
- `water_adjacent` — free tiles touching water, as `{x, y, water}`. `water` is the excitement bonus and it STACKS: a tile between two water tiles is +2. The list is sorted best-first — spend these entirely on RIDES, and never on a shop or staff, which gain nothing from water.
- `unreachable_tiles` — buildable tiles guests can never walk to: whatever sits here earns $0 for the rest of the run and buys cumulative capacity only. Site here ONLY as the DESTINATION of an eviction `move` that frees a reachable tile for a higher tier. Don't place shops or new rides here.
- `placed_rides` and `path_coords` — tiles to place the staff on.
- each placed ride/shop also carries `capacity`, `excitement`, `profit` and `guests_entertained` — use them to rank which asset is worth siting near, and which is the worst performer to remove.

## Tips:
### Placing attractions/staff:
- Hunger and thirst keep rising in line, so placing food and drink shops near high-capacity rides with long lines matters most.
- Place rides next to water: +1 excitement per adjacent water tile, stacking. Excitement is what makes a guest pick that ride over another, so take the highest-`water` tile in `water_adjacent` before any plain free tile.
- Guests favor novelty — kinds of attractions they haven't visited before — and nearby attractions, but never visit the same attraction twice in a row. When possible, don't place identical rides beside each other.
- Place specialty shops only at high-traffic junctions, as guests do not actively seek out specialty shops; they visit them only if they pass by.
- Place diverse rides/shops across subtypes and subclasses together.
- Place a janitor on the ride/shop with the lowest cleanliness.
- Place a mechanic at the ride with the lowest uptime.
- Place a specialist at the ride with the highest avg_wait_time.
- High-capacity rides sit idle waiting to fill, so only build them where demand is high; in low-traffic spots a smaller ride runs more often.
- Multiple staff can occupy and work on the same tile at any given time.
- Rides is given preference for a tile over a shop.

#### For tier upgrades for rides:
Every placed ride carries `reachable`:
  - `true` — guests walk to it; it earns and it occupies a scarce tile.
  - `false` — already stranded: $0 for the rest of the run, capacity only. Evicting one frees nothing.

Trigger: `free_tiles` is empty AND a higher tier is unlocked.
1. Among `reachable: true` rides ONLY, pick the LEAST `profit`. Tie-break on fewest `guests_entertained`. Never your best tier.
2. `move` it to an `unreachable_tile` — you keep its capacity and give up only the park's smallest revenue.
3. Return BOTH pairs: `x,y` = its CURRENT tile from `placed_rides`; `new_x,new_y` = the `unreachable_tile`.
4. That tile is free next turn — place the new tier on it then.

#### For tier upgrades for shops:
1. If the coordinator named a SPECIFIC asset (e.g. a tier-upgrade swap: "remove the yellow drink shop") and only one matches, return THAT one's (x,y).
2. If several match that name, pick the one with the least profit among THOSE matches.
3. If the coordinator asked to cull an underperformer without naming a type, pick the one with the least profit among ALL placed shops. Tie-break on fewest guests_entertained. Return the selected asset's (x,y) to be removed.

#### For firing staff: 
Use `remove` → find the matching subtype/subclass in status_layout.placed_staff and return its (x,y). If several match, tie-break on `success_metric_value`.

## Learned rules (promoted from prior runs)
