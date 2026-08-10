# Rides Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which rides to build, upgrade, move, or remove — subtype, tier (never coordinates). Rides are the park's main draw and its biggest rating lever: diversify subtypes/tiers, push to higher tiers as research unlocks them, keep them repaired, and never let num_rides hit 0.
<!-- PLAYBOOK_SUMMARY:END -->

Rides are the **core of the amusement park**, determining how many guests visit. They improve guest happiness and contribute to the overall value of the park.

## Types of rides:
- **Carousels:** cheapest to build/operate, rarely break, but limited excitement and capacity.
- **Ferris Wheels:** intermediate cost, highest capacity.
- **Roller Coasters:** expensive, highest excitement/intensity, frequent breakdowns.

## Key attributes:
- **Capacity:** Guests per ride run. Higher capacity means shorter guest waits. Total park capacity determines how many guests visit. Only rides can raise it, and no new guest can enter while the park sits at capacity — so guest inflow stalls until you build a ride.
- **Excitement:** Higher excitement increases guest happiness and park rating.
- **Intensity:** Keep average intensity balanced (~5) to improve park rating.
- **Ticket price:** Always set to `max_ticket_price`.

## Park current status (not set by you)
- **park_capacity** — the park's cumulative ride capacity; caps guest inflow.
- **avg_intensity** — park-wide average ride intensity; steer it toward ~5.
- **capacity** — that ride's own capacity, i.e. what it contributes to `park_capacity`.
- **profit** — earnings minus running cost for that ride.
- **guests_entertained** — guests served = popularity.
- **avg_wait_time** — average queue wait; long waits raise guests' hunger/thirst and can turn guests away (consider building another of that ride) and flag a ride that's under capacity for its demand (remove it during tier upgrades).
- **next_unlock** — the next tier due and which subtype unlocks next, e.g. `"next_unlock": {"tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. `days` is the ETA for the first listed unlock. Absent = research off.

## Tips:
- **Guests leave** when money, energy, hunger, thirst, or happiness runs critical. Hunger/thirst rise and happiness falls over time, so food/drink shops and rides are what keep guests in the park spending. Keep this in mind while building rides.
- Since only rides increase capacity, a park with no rides will receive no visitors.
- Building multiple rides of the same kind (i.e., identical subtype and subclass) yields diminishing returns for your park rating. Whenever possible, **DIVERSIFY** your rides across subtypes and subclasses for a higher overall rating.
- When research unlocks a higher tier (yellow < blue < green < red; see `available_entities`) and cash allows, place it.
- Tier upgrade (usually 2 steps): with every tile occupied, `move` your least profitable reachable ride onto an unreachable tile, then `place` the new tier on the tile it freed next turn. Name the ride by subtype/subclass in your `rationale`; the layout planner picks both tiles.
- **Building on unreachable tiles:** once reachable tiles are full, keep building there — guests never arrive, so the ride earns $0, but it still adds park capacity. Buy that capacity only once your reachable core is performing, say so explicitly in your `rationale`, and never send your BEST unlocked tier there.
- High-capacity rides sit idle waiting to fill, so only build them where demand is high; in low-traffic spots a smaller ride runs more often. An `avg_guests_per_operation` far below `capacity` means the ride is OVERSIZED for current demand — the fix is more guests (rating/excitement) or a cheaper smaller ride.
- A ride sells for only 66% of its building cost, so a swap burns 34% plus a whole turn. Avoid removal.

## Learned rules (promoted from prior runs)
