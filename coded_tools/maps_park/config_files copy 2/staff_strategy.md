# staffing_manager - policy

Prefer long-term compounding investments over conservative short-term plays. Idle steps are permanently lost value.

## Staff mechanics
All staff have a daily salary; some have per-action operating costs. Multiple staff can occupy the same tile.

Three types:
- **Janitor:** walks to dirty tiles and cleans them. Higher tier cleans faster (red does preventive cleaning).
- **Mechanic:** walks to broken (out-of-service) rides and repairs them over several ticks. NO preventative maintenance. Higher tier repairs faster.
- **Specialist**:
  - Yellow (Clown): boosts happiness of guests queued/boarded at rides.
  - Blue (Stocker): restocks shops below their inventory threshold.
  - Green (Park Crier): gives guests status info — they avoid out-of-service/dirty attractions and favour shorter queues.
  - Red (Vendor): serves food + drink to guests waiting at rides (reduces hunger & thirst).

For Janitor & Mechanic, subclass is a quality tier (yellow < blue < green < red); blue/green/red walk at 2× speed.

- Hire = `place(type='staff', subtype, subclass, x, y, price=<salary>)`. Dismiss = `remove(type='staff', subtype, subclass, x, y)`. Salary MUST come from `economics_staff` — never hardcode.
- Place on path tiles adjacent to work area (`path_coords`): janitors near busiest cluster; mechanics near highest-breakdown coaster; specialists near relevant ride/shop.
- Don't hire any staff before ride revenue is established or speculatively.
- Dismiss when cash is tight and park is clean/fully repaired — use exact (x,y) from `placed_staff`.

## Learned rules (promoted from prior runs)
- 2nd mechanic on uptime slide: with 15+ rides and only one mechanic, if min_uptime drops >=0.30 in one turn (or falls below 0.60), hire a 2nd mechanic that same turn rather than waiting for it to recover on its own; one mechanic cannot keep pace with 15+ rides. (learned ep0)
- Early janitor override: drop the step-10 gate when min_cleanliness has fallen <= 0.30 with 3+ attractions and 0 janitors — hire the first janitor that turn regardless of step, because the cleanliness crash floors park_rating well before step 10. (learned ep0)
- Hard cleanliness override: if min_cleanliness drops to <= 0.70 with only one janitor on payroll, hire a 2nd janitor THAT turn regardless of attraction count or the 2-turn-trend test; the 0.80/2-turn rule reacts too slowly when cleanliness is already falling fast. (learned ep0)
