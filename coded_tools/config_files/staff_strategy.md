# Staffing Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You hire and dismiss janitors, mechanics, and specialists (salary + path-adjacent placement). Staff are how you defend park_rating — janitors keep it clean, mechanics keep rides running, specialists lift happiness. Hire only once revenue supports it, and don't over- or under-staff.
<!-- PLAYBOOK_SUMMARY:END -->

## Staff mechanics
All staff carry a daily salary (and sometimes a per-action operating cost) that is charged whether or not there is work for them — so a hire made before there is dirt/breakdowns/guests for it to act on drains cash without defending much rating, and a staff member whose salary exceeds the rating it protects is a net drag.

Three types:
- **Janitor:** walks to dirty tiles and cleans them (a dirty park lowers park_rating). Higher tier cleans faster (red does preventive cleaning).
- **Mechanic:** walks to broken (out-of-service) rides and repairs them over several ticks (frequent out-of-service rides lower park_rating). Higher tier repairs faster (red does preventative maintenance).
- **Specialist:** lift guest happiness, raising park_rating.
  - Yellow (Clown): boosts happiness of guests queued/boarded at rides.
  - Blue (Stocker): restocks shops below their inventory threshold.
  - Green (Park Crier): gives guests status info — they avoid out-of-service/dirty attractions and favour shorter queues.
  - Red (Vendor): serves food + drink to guests waiting at rides (reduces hunger & thirst).

## Tier upgrades
Tiers hierarchy: yellow < blue < green < red. A higher tier of a role does its job faster/wider (e.g. red janitors/mechanics do preventive work), so it defends rating harder per hire once it appears in `available_entities`. Staff share tiles (many per tile), so placement is never tile-constrained.

## Learned rules (promoted from prior runs)
When park rating has been stuck below the healthy threshold for several turns while cash covers a wage, add a mechanic or specialist rather than another same-tier shop to raise the rating multiplier on all guest spend. (learned ep2)
Hire a janitor as soon as minimum cleanliness falls below half and cash covers the wage, before placing further shops, to restore cleanliness and lift park rating. (learned ep2)
