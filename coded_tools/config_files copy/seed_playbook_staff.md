# Staffing Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You hire and dismiss janitors, mechanics, and specialists (salary + path-adjacent placement). Staff are how you defend park_rating — janitors keep it clean, mechanics keep rides running, specialists lift happiness. Hire only once revenue supports it, and don't over- or under-staff.
<!-- PLAYBOOK_SUMMARY:END -->

Staff are necessary for the smooth operation of your park, ensuring attractions run properly and guests remain satisfied. All staff carry a daily salary (and sometimes a per-action operating cost). They improve park rating.

## Subtypes of staff:
- **Janitors:** Move through the park toward dirty areas to clean them. Red tier does preventive cleaning.
- **Mechanics:** Move toward rides that are broken down to repair them. Red tier does preventive repairing.
- **Specialists:** Perform different roles based on subclass:
  - Yellow (Clowns): increase the happiness of guests waiting in line.
  - Blue (Stockers): restock shops with low inventory. (10% of order quantity)
  - Green (Park Criers): inform guests about out-of-service or dirty attractions, as well as the current line wait time for rides.
  - Red (Vendors): provide food and drink to guests waiting in line.
A dirty park, frequent out-of-service rides/shops, long wait lines **significantly decrease park rating**.

## Park current status (not set by you)
- **salary** + **operating_cost** — fixed daily cost by role+tier plus extra cost per action performed.
- **min_cleanliness** — worst tile cleanliness in the park; if low, hire a janitor whose `cleaning_threshold` is ABOVE the level you need it back at.
  - **Dirt compounds:** unhappy guests litter → dirtier park → unhappier guests, and a too-dirty ride turns guests away. Cleanliness slipping is a janitor decision, not a wait-and-see.
- **min_uptime** — worst uptime across rides/shops. If low:
  - `out_of_service` = true, hire a mechanic
  - otherwise a shop ran dry, hire blue specialist to restock the shops.
  - or a ride broke earlier today and was already repaired (mechanic hired already).
- **success_metric / success_metric_value** — work done so far (e.g. `amount_cleaned`). Dismiss the worst based on this metric.
- **cleaning_threshold** (in `staff_economics`) — CEILING a janitor cleans a tile to. It skips tiles already at its threshold. Eg: yellow **cannot** lift `min_cleanliness` past 0.85. If you want better, upgrade the tier.

## Tier upgrades
Tier hierarchy: yellow < blue < green < red.
A higher tier of a role does its job faster/wider/better (e.g. red janitors/mechanics do preventive work), and specialists each have different responsibilities, defending park rating better. If a new tier unlocks in the `available_entities`, place it well.
Each hire gets limited actions/day, one tile walked is 1 action. Blue & higher tier janitors/mechanics move at double speed. 

## Learned rules (promoted from prior runs)
When a red carousel drops min_uptime below 0.95, pause ride placement and place nearby yellow mechanics until min_uptime recovers to at least 0.97. (learned ep2)
Hire janitors and mechanics early and add more as ride density grows so cleanliness and uptime recover before salaries threaten rewards. (learned ep0)
