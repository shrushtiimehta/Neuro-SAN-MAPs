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
- Remove actions require explicit integer (x,y): when issuing remove(type, subtype, subclass), supply the target attraction's exact (x,y) tile from the snapshot; remove with x=None/y=None is rejected ("argument x of type NoneType but expected type int") and wastes the turn as a wait. (learned ep1)
- When placing a janitor/mechanic/staff, supply (x,y) that is a path tile or inside an existing attraction from the snapshot (NOT an empty valid_placement_coords tile, which is valid only for rides/shops); staff placed on an empty buildable tile is rejected with "Invalid location for staff. Must be on a path or in an attraction." (learned ep1)
