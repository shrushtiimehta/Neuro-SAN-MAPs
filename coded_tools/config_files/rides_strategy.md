# Rides Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which rides to build, upgrade, or remove — subtype, tier, and ticket price (never coordinates). Rides are the park's main draw and its biggest rating lever: diversify subtypes/tiers, push to higher tiers as research unlocks them, keep them repaired, and never let num_rides hit 0.
<!-- PLAYBOOK_SUMMARY:END -->

Only 100 steps per episode — make each a high-impact moves; don't micromanage.

## Types of rides:
- **Carousels:** cheapest to build/operate, rarely break.
- **Ferris Wheels:** intermediate, highest capacity.
- **Roller Coasters:** expensive, highest excitement/intensity, frequent breakdowns.

## Ride status readouts (reported per ride, not set by you)
- **Ticket price** — `max_ticket_price` from `economics_rides` is applied automatically; higher tiers carry a higher cap, so they earn more per guest.
- **revenue_generated / operating_cost** — earnings vs running cost; `revenue_generated - operating_cost` is net contribution — how you rank which ride to cull for a higher-tier swap.
- **intensity** — try to keep the park-wide *average* intensity balanced (~5), since too high or too low drops rating.
- **excitement** — higher score lifts guest happiness and park_rating.
- **guests_entertained** — how many guests the ride actually served = its real popularity/throughput.
- **avg_wait_time** — average queue wait; long waits raise guests' hunger/thirst and can turn guests away (consider building another of that ride) and flag a ride that's under capacity for its demand (remove it during tier upgrades)

## Tier upgrades
- At the start, place low-tier/basic rides, even repeated ones.
- Identical rides (same subtype and tier) add little to the park rating. When available, vary the subtype/tier → more guests → more revenue → more reward. When research unlocks a higher tier (yellow < blue < green < red; see `available_entities`) and cash allows, place it fast.
- If every tile is full (tile space is scarce) and a higher-tier ride needs placing, it costs a two-turn swap — remove the least profitable / most-redundant ride, then place the higher tier next turn.
- Value from a placement earns for the rest of the episode; a step spent idle earns nothing back.

## Learned rules (promoted from prior runs)