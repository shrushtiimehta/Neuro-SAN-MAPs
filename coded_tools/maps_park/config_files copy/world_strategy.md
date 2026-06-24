# park_layout_planner - policy

The path and water layout is FIXED in this game mode (terraform actions do not
exist here). You arrange assets on the existing layout with place/move/remove/
modify only — you never create or remove paths or water.

- **Work the existing paths:** place rides/shops on `valid_placement_coords`, which are the empty tiles adjacent to the pre-built path network, so guests can reach every attraction without backtracking.
- **Shop proximity:** place drink/food shops within 15-20 tiles of every ride cluster so guests can satisfy thirst/hunger without long detours.
- **Specialty placement:** place specialty/yellow (souvenir) shops at high-traffic path junctions.
- **Water adjacency:** rides adjacent to water gain excitement (which feeds guest happiness, a rating driver), so prefer placing rides on empty tiles next to EXISTING water. Water cannot be created or removed here — just exploit the water tiles the layout already has.
- **Ride clustering:** cluster rides of different subtypes together to diversify intensity and maximise park rating.
- **Coordinate lookups for existing entities:**
  - `move`: supply current (x,y) from `placed_rides` AND a suitable (new_x,new_y) e.g. adjacent to a water tile.
  - `modify`: look up the attraction's current (x,y) from `placed_rides` or `placed_shops`.
  - `remove`: return the attraction's current (x,y) from the snapshot.

## Learned rules

## Learned rules (promoted from prior runs)
- Remove actions require explicit integer (x,y): when issuing remove(type, subtype, subclass), supply the target attraction's exact (x,y) tile from the snapshot; remove with x=None/y=None is rejected ("argument x of type NoneType but expected type int") and wastes the turn as a wait. (learned ep1)
- When placing a janitor/mechanic/staff, supply (x,y) that is a path tile or inside an existing attraction from the snapshot (NOT an empty valid_placement_coords tile, which is valid only for rides/shops); staff placed on an empty buildable tile is rejected with "Invalid location for staff. Must be on a path or in an attraction." (learned ep1)
