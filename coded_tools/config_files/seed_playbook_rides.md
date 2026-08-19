# Rides Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which rides to build, upgrade, move, or remove — subtype, tier (never coordinates). Rides are the park's main draw and its biggest rating lever: diversify subtypes/tiers, push to higher tiers as research unlocks them, keep them repaired, and never let num_rides hit 0.
<!-- PLAYBOOK_SUMMARY:END -->

Rides are the **core of the park**. They are the only source of capacity, so a park with no rides gets no visitors — and they lift guest happiness, park rating and park value.
Identical rides gives diminishing park-rating returns. Keep rides **DIVERSE**. Prefer placing higher tier rides.

## Types of rides:
- **Carousels:** cheapest to build and run, rarely break, but low excitement and capacity.
- **Ferris Wheels:** mid cost, highest capacity.
- **Roller Coasters:** expensive, highest excitement and intensity, break most often.

## Key attributes:
- **Capacity:** guests per run, and the only thing that raises `park_capacity` — no new guest enters while the park sits at capacity.
- **Excitement:** finishing a ride adds guest happiness — feeds park rating.
- **Intensity:** rating drops as park-wide `avg_intensity` drifts from ~5.
- **Ticket price:** fixed per subclass (`max_ticket_price` in `rides_economics`) — a higher tier charges more.

## Park current status (not set by you)
- **park_capacity**, **avg_intensity** — park-wide totals.
- **placed_rides** — each carries `capacity`, `excitement`, `intensity`, `ticket_price`, `avg_wait_time`, `avg_guests_per_operation`, `reachable`, and `guests_entertained` (guests carried today = popularity; resets each morning).
- **broken_rides** — rides currently out of service, with `uptime`.
- **next_unlock** — the next tier due and which subtypes still need it, e.g. `{"subtype": "carousel", "tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Absent = research is off. Use to plan ahead.

## Tier upgrade:
- Place a higher tier **as soon as** research unlocks it (yellow < blue < green < red; see `available_entities`) and cash allows — higher tiers pay back far more - place them as much as and as soon as possible. Each tier has its own distinct benefits, listed in `economics_rides`; read them and exploit them.
- **HOW TO PLACE HIGHER TIERS?**
    1. `move` your lowest-tier ride onto an `unreachable_tiles` slot.
    2. `place` the new tier on the tile it vacated.
A `move` is free and carries the ride's capacity with it. More number of rides (reachable or unreachable) increase revenue.
- Avoid `remove`: a ride sells back for only 66% of its build cost and the park loses its capacity.

## Learned rules (promoted from prior runs)
