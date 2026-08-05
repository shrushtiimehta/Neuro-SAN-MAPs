# Staffing Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You hire and dismiss janitors, mechanics, and specialists (salary + path-adjacent placement). Staff are how you defend park_rating — janitors keep it clean, mechanics keep rides running, specialists lift happiness. Hire only once revenue supports it, and don't over- or under-staff.
<!-- PLAYBOOK_SUMMARY:END -->

Goal: Improve park rating by keeping the park clean, rides running and guests entertained.

## Park status readouts (not set by you)
- **min_cleanliness** — worst tile cleanliness in the park; low → hire a janitor.
- **min_uptime** — worst uptime across rides and shops; low with `out_of_service` true → a ride is down (mechanic); low with `out_of_service` false → a shop ran dry (blue-specialist stocker).
- **out_of_service** — true if any ride is out of service right now; true → hire/deploy a mechanic. A single park-wide breakdown flag, no per-ride list needed.

## Staff status readouts (`placed_staff` — reported per hire, not set by you)
Use these to judge whether a hire is earning its keep; if not, dismiss the worst:
- **salary** — fixed daily cost by role+tier.
- **operating_cost** — extra cost per action performed.
- **success_metric / success_metric_value** — work done so far (e.g. `amount_cleaned`).

## Staff hiring
All staff carry a daily salary (and sometimes a per-action operating cost). Hire only when there is dirt, a ride breakdown, or too many guests to defend rating.

Types of staff:
- **Janitor:** Cleans the park. A dirty park sharply lowers park_rating.
- **Mechanic:** Repairs rides. Frequent out-of-service rides sharply lower park_rating.
- **Specialist:** Lifts guest happiness, raising park_rating.
  - Yellow (Clown): boosts happiness of guests queued/boarded at rides.
  - Blue (Stocker): restocks shops below their inventory threshold.
  - Green (Park Crier): gives guests status info — they avoid out-of-service/dirty attractions and favour shorter queues.
  - Red (Vendor): serves food + drink to guests waiting at rides (reduces hunger & thirst).

## Tier upgrades
Tiers hierarchy: yellow < blue < green < red.
A higher tier of a role does its job faster/wider (e.g. red janitors/mechanics do preventive work), so it defends rating harder per hire once you place it in the park. If a new tier unlocks in the `available_entities`, place it fast.
Staff share tiles (many per tile), so placement is never tile-constrained.

## Learned rules (promoted from prior runs)
When min_cleanliness slips below ~0.78 while cash allows, add a janitor within two turns to restore cleanliness so shop order_quantity scaling stays unthrottled. (learned ep5)
Hire an additional mechanic when ride and shop count outgrows current mechanic coverage to hold min_uptime high before breakdowns cut revenue. (learned ep0)
Hire a janitor immediately when min_cleanliness falls below the low-cleanliness threshold to arrest rating decay before it starves guest inflow. (learned ep0)
Hire a mechanic and a janitor as soon as the first breakdown or dirt appears, and scale staff with fleet size so rides stay in service and tiles stay clean. (learned ep0)
