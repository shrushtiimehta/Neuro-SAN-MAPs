# Rides Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which rides to build, upgrade, move, or remove, including their subtype and tier—but never their coordinates. Rides are the park's main draw and its biggest rating lever: diversify subtypes and tiers, advance to higher tiers as research unlocks them, keep rides repaired, and never let `num_rides` reach 0.
<!-- PLAYBOOK_SUMMARY:END -->

Rides are the **core of the park**. They determine park capacity, which allows guests to enter, and help increase park rating and value. Prefer placing a diverse selection of higher-tier rides.

## Types of rides:
- **Carousels:** cheapest to build/operate, rarely break, low excitement and capacity.
- **Ferris Wheels:** moderately expensive, highest capacity.
- **Roller Coasters:** expensive, highest excitement and intensity, break most often.

## Key attributes:
- **Capacity:** number of guests allowed per ride cycle. Adds to `park_capacity` in `status_rides`, which determines how many guests can enter the park.
- **Excitement:** completing a ride increases guest happiness and park rating.
- **Intensity:** maintain `avg_intensity` in `status_rides` at approximately 5.
- **Ticket price:** fixed and listed in `rides_economics`.

## Current park status is in `status_rides`:
- **guests** — guest satisfaction and activity metrics.
- **placed_rides** — per-ride status and performance metrics.

## Tier upgrade:
- Place higher-tier rides **as soon as** research unlocks them and cash allows (yellow < blue < green < red). In `status_rides`, check `available_entities` for unlocked tiers and `next_unlock` to prepare for upcoming unlocks. Higher tiers pay back far more and offer distinct benefits; review `economics_rides` and exploit those benefits.
- **HOW TO PLACE HIGHER TIERS?**
    1. `move` your lowest-tier ride onto an `unreachable_tiles` slot.
    2. `place` the new tier on the tile it vacated.
A `move` is free and preserves the ride's capacity. Greater number of rides, whether reachable or unreachable, increases the number of visiting guests.
- Avoid `remove` because it decreases `park_capacity`.

## Learned rules (promoted from prior runs)
When a late reachable ride slot has already been freed and upkeep is not urgent, place a red carousel in it immediately before spending on optional shops, staff, or coasters. (learned ep8)
Attempt late move-then-replace ride upgrades only when an empty bank tile exists; otherwise skip ride replacement instead of risking move or placement errors. (learned ep0)
Reinvest early profits into reachable ride capacity and carousel tier replacements, moving weaker rides to bank tiles before placing stronger carousels. (learned ep0)
