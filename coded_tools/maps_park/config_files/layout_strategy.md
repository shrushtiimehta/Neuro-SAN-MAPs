# park_layout_planner - policy

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

## Learned rules

## Learned rules (promoted from prior runs)
When placing a ride or shop, prioritize tile coordinates that are confirmed free (not path, not water, not already occupied); if a placement was rejected at a specific tile, never retry that exact tile for the remainder of the episode — always select a different candidate tile from the available free-tile list. (learned ep0)
