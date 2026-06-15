# staffing_manager - policy

- **Action API:** staff are added via `place(type='staff', subtype, subclass, x, y, price=<salary>)` - the `price` field is the salary and is REQUIRED. Staff are dismissed via `remove(type='staff', subtype, subclass, x, y)`. There is no hire/fire action.
- **Salary source:** the `price` (salary) for each (subtype, subclass) MUST come from `state_read(name='economics_staff')`. Never hardcode or estimate.
- **Placement:** staff patrol the path network - place them ON path tiles adjacent to their work area. Use `path_coords` from the snapshot to find the nearest path tile to the target attraction (no grid scanning needed).
  - janitors: path tile adjacent to the busiest attraction cluster
  - mechanics: path tile adjacent to the roller_coaster with highest breakdown_rate
  - specialists: path tile adjacent to the relevant ride or shop
- **When to hire first staff:**
  - First janitor: ONLY when 3+ attractions are placed AND at least 10 steps have passed.
  - Second janitor: hire when `min_cleanliness ≤ 0.80` for 2+ consecutive turns AND ≥2 rides operational (Priority 2.5). Cleanliness <0.8 starts a per-tile rating penalty (up to 25 pts); $15/turn is cheap. Do NOT react in the stable 0.81-0.87 band. If the park is full (free_tiles=0, no free path tile) hiring is impossible - a full park tolerates lower cleanliness, so don't panic-wait on cleanliness while all rides are healthy.
  - First mechanic: ONLY when a roller_coaster is placed (high breakdown rate). Yellow/blue carousels rarely break - do not hire mechanics speculatively.
  - Specialists (clown, stocker, park_crier, vendor): defer until after step 20 and only when the relevant attractions exist.
  - Do NOT hire any staff before ride revenue is established.
- **Ratios (adjust on observed cleanliness and breakdown rate):**
  - 1 janitor per 3-4 ride/shop clusters
  - 1 mechanic per 5-8 rides (more if roller_coasters are present)
  - Dismiss staff when cash is tight and the park is clean / fully repaired; get the staff member's exact (x,y) from `placed_staff` for the remove call.

## Learned rules (promoted from prior runs)
- 2nd mechanic on uptime slide: with 15+ rides and only one mechanic, if min_uptime drops >=0.30 in one turn (or falls below 0.60), hire a 2nd mechanic that same turn rather than waiting for it to recover on its own; one mechanic cannot keep pace with 15+ rides. (learned ep0)
- Early janitor override: drop the step-10 gate when min_cleanliness has fallen <= 0.30 with 3+ attractions and 0 janitors — hire the first janitor that turn regardless of step, because the cleanliness crash floors park_rating well before step 10. (learned ep0)
- Hard cleanliness override: if min_cleanliness drops to <= 0.70 with only one janitor on payroll, hire a 2nd janitor THAT turn regardless of attraction count or the 2-turn-trend test; the 0.80/2-turn rule reacts too slowly when cleanliness is already falling fast. (learned ep0)
