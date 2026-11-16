# Staffing Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You hire and dismiss janitors, mechanics, and specialists while accounting for salaries and path-adjacent placement. Staff defend `park_rating`: janitors keep the park clean, mechanics keep rides running, and specialists improve guest happiness. Hire only when revenue supports the cost, and avoid overstaffing or understaffing.
<!-- PLAYBOOK_SUMMARY:END -->

Staff are necessary for the smooth operation of your park, ensuring that attractions remain clean and operational and that guests remain entertained. They help improve the park rating.

## Subtypes of staff:
- **Janitors:** Clean dirty areas.
- **Mechanics:** Repair broken rides.
- **Specialists:** Perform different roles based on subclass:
  - Yellow (Clowns): increase the happiness of guests in line.
  - Blue (Stockers): provide limited restocking for shops with low inventory.
  - Green (Park Criers): inform guests about dirty or out-of-service attractions and ride wait times.
  - Red (Vendors): provide food and drinks to guests in line.
A dirty park, frequent out-of-service rides or shops, and long wait lines **significantly decrease park rating**. Staff help control these problems and support the entire park and increase guest spend.

## Current park status in `status_staff`:
- **min_cleanliness** — worst tile cleanliness in the park; if low, hire a janitor.
  - **Dirt compounds:** unhappy guests litter → dirtier park/rides → guests turned away → unhappy guests. ACT FAST.
- **min_uptime** — worst uptime across rides/shops. If low:
  - If a ride’s `out_of_service` value is true, the ride is broken; hire a mechanic.
  - Otherwise, a shop may have run dry; hire a blue specialist to restock shops.
  - Alternatively, a ride may have broken earlier in the day and already been repaired by a mechanic.
- **success_metric** and **success_metric_value** — work completed so far (for example, `amount_cleaned`).

## Tier upgrades (yellow < blue < green < red)
A higher tier of a role works faster, covers a wider area, or performs more effectively. Each specialist tier also has different responsibilities that help defend park rating. When a new tier appears in `available_entities`, place it instead of the lower tier.
Each hire receives a limited number of actions per day. Blue-tier and higher-tier janitors and mechanics move at double speed.
Green-tier janitors have higher cleaning thresholds, which determine the level to which they clean a tile. For example, a yellow janitor **cannot** raise `min_cleanliness` above 0.85.
Red-tier janitors and mechanics provide preventive cleaning and maintenance.
For more details, review `economics_staff`.

## Learned rules (promoted from prior runs)
