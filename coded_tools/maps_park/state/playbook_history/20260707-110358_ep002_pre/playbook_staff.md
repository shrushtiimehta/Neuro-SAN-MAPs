# staffing_manager - policy

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary (regenerated every episode)
Scale staff to ~10 to hold park_rating in the low-30s (ep0 finished 10 staff, rating ~35). Place janitor+mechanic early (steps 11-12), then specialists at steps ~41/51/59 and extra janitors/mechanic (ep0 step65 mechanic +759, step70 janitor +1198). Place staff only on valid path/attraction tiles — ep1 steps 10,11 were rejected for invalid staff location. Add staff when rating dips below ~30, not blindly.
<!-- PLAYBOOK_SUMMARY:END -->

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

## How you move park_rating (status carries `park_rating`)
Staff are how you stop rating from being dragged down:
- **Janitors → cleanliness:** a dirty park lowers rating. Hire a janitor early and keep one so the park stays clean.
- **Mechanics → repairs:** they repair broken (out-of-service) rides; frequent out-of-service rides lower rating. No preventive maintenance — staff a mechanic before coasters start breaking.
- **Specialists → guest happiness:** clown (queue happiness), vendor (serves waiting guests), park crier (steers guests off dirty/out-of-service attractions).
Use `park_rating` as the trigger: sagging + dirty → janitor; sagging + broken rides → mechanic.

## Learned rules (promoted from prior runs)
Hire an additional janitor whenever min_cleanliness drops below 0.5 so back-half park rating is never capped by dirt. (learned ep10)
Hire janitors and mechanics proactively in the first half so park_rating is stabilized before the back half, keeping the drink/food modify revenue engine running through to the end of the episode. (learned ep4)
When min_cleanliness falls below 0.3 and no janitor is employed, hire a janitor immediately to restore cleanliness and let park_rating recover. (learned ep1)

## Learned rules (promoted from prior runs)
When min_uptime drops below 0.8 and roller_coasters are present, add a mechanic immediately.
