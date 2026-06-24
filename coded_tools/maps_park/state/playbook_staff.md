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

For Janitor & Mechanic, subclass is a quality tier (yellow < blue < green < red); blue/green/red walk at 2× speed. When a new tier appears in `available_entities`, dismiss the lowest-tier existing staff of that subtype and replace with the new tier — don't just add alongside.

- Hire = `place(type='staff', subtype, subclass, x, y, price=<salary>)`. Dismiss = `remove(type='staff', subtype, subclass, x, y)`. Salary MUST come from `economics_staff` — never hardcode.
- Place on path tiles adjacent to work area (`path_coords`): janitors near busiest cluster; mechanics near highest-breakdown coaster; specialists near relevant ride/shop.
- Don't hire any staff before ride revenue is established or speculatively.
- Dismiss when cash is tight and park is clean/fully repaired — use exact (x,y) from `placed_staff`.

## Learned rules (promoted from prior runs)

## Learned rules (promoted from prior runs)
When min_uptime drops below 0.8 and roller_coasters are present, add a mechanic immediately.
