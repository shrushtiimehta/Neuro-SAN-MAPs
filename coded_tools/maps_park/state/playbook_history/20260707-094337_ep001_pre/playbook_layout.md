# park_layout_planner - policy

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary (regenerated every episode)
Keep placements on free tiles - last ep hit a path-collision rejection at step 60. Cluster rides and shops so guests flow past shops (drives shop revenue). When removing weak carousels (turns ~46/62), free up good central tiles for higher-value placements rather than fragmenting paths.
<!-- PLAYBOOK_SUMMARY:END -->

The path and water layout is FIXED in this game mode. You arrange assets on the existing layout with place/move/remove/
modify only — you never create or remove paths or water.

- Guests travel entrance → attractions → exit; place attractions to intercept this flow.
- Place rides/shops on `free_tiles` (empty tiles adjacent to path). On ride upgrades, replace the least profitable ride.
- Place drink/food shops near ride clusters; place specialty shops at high-traffic path junctions.
- Prefer placing rides adjacent to water — each adjacent water tile adds +1 excitement.
- Cluster rides of different subtypes to diversify intensity and maximise park rating.
- Coordinate sources by action:
  - `place` rides/shops: (x,y) from `free_tiles`.
  - `place` staff: (x,y) from `path_coords` or inside an existing attraction — NOT from `free_tiles` (rejected).
  - `move`: current (x,y) from placed list; new (x,y) from `free_tiles` or adjacent to water.
  - `modify` / `remove`: (x,y) from the relevant placed list.

## How you move park_rating (status carries `park_rating`)
Placement touches park_rating three ways:
- **Water adjacency:** each water tile adjacent to a ride raises that ride's excitement by 1, which raises happiness and rating — prefer placing rides next to water.
- **Diversity / intensity:** cluster DIFFERENT ride subtypes so the fleet's average intensity stays near 5, and avoid identical rides (same subtype+tier), which give diminishing returns.
- **Flow:** keep attractions on the guest path (entrance → exit) and reachable — more visits ⇒ happier guests ⇒ higher rating.

## Learned rules

## Learned rules (promoted from prior runs)
Before any place or staff action, target a known-empty buildable tile (not a path, water, ride, or shop) to avoid occupied/invalid-tile rejections that waste the step. (learned ep5)
When placing a ride or shop, prioritize tile coordinates that are confirmed free (not path, not water, not already occupied); if a placement was rejected at a specific tile, never retry that exact tile for the remainder of the episode — always select a different candidate tile from the available free-tile list. (learned ep0)
