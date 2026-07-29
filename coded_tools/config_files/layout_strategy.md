# Park Layout Planner

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You own ALL (x,y) placement on the fixed path — place/remove only, never new paths or water. Put attractions on the guest flow (entrance→exit), place rides next to water for excitement, and never reuse a tile that was already rejected.
<!-- PLAYBOOK_SUMMARY:END -->

- Guests travel entrance → attractions → exit; place attractions to intercept this flow.
- Place different rides/shops in clusters to diversify intensity and maximise park rating. Place them always on free tiles.
- Shops: Place drink/food near ride clusters, where long lines have already built hunger/thirst or near rides that have the longest avg_wait_time. Place specialty shops only at high-traffic junctions as they get visited in passing.
- Rides: Place rides next to a water tile to gain +1 excitement, which in turn increases rating.
- Staff — place them ONLY on a ride or shop tile in placed_rides/placed_shops (many staff can share one tile):
    - Place a janitor on the ride/shop with the lowest cleanliness.
    - Place a mechanic at the ride with the lowest uptime.
    - Place a specialist at the ride with the highest avg_wait_time to entertain the guests.
- `remove` for rides/shop — the owning manager (rides/shops) decides WHICH asset to drop (a specific tier-swap target, or the least-profitable / most-redundant one); you only resolve it to a tile and execute.
    1. If the coordinator named a SPECIFIC asset (e.g. a tier-upgrade swap: "remove the yellow carousel") and only one matches, return THAT one's (x,y).
    2. If several match that name, pick the one with least (revenue_generated-operating_cost) among THOSE matches.
    3. If the coordinator asked to cull an underperformer without naming a type, pick the one with least (revenue_generated-operating_cost) among ALL placed rides/shops. Tie-break on fewest guests_entertained.
    Return the selected asset's (x,y) to be removed.
- `remove` staff → find the matching subtype/subclass in status_layout.placed_staff and return
    its (x,y) (if several match, return any). The worst-by-profit rule above is rides/shops only — staff have no revenue.


## Learned rules (promoted from prior runs)
