# rides_manager - policy

## Ride mechanics
1. **Capacity** — guests per cycle; drives op frequency and park draw.
2. **Excitement** — raises happiness + rating; ride gains +1 excitement per adjacent water tile.
3. **Intensity** — per-ride score; influences which guests choose it.
4. **Ticket price** — always set to `max_ticket_price`.
5. **Cost per operation** — deducted each cycle.

Cycle behaviour: rides operate only when guests have boarded; they wait a few turns to fill up (longer for higher capacity). Rides can break down — guests turn away and rating drops; mechanics repair them. Repair cost and downtime are proportional to building cost.

Three subtypes:
- **Carousels:** cheapest to build/operate, rarely break, low excitement/capacity.
- **Ferris Wheels:** intermediate, highest capacity of any subtype.
- **Roller Coasters:** expensive, highest excitement/intensity, frequent breakdowns.

- Price is always = `max_ticket_price` from `economics_rides` (sim rejects higher).
- Always build the highest UNLOCKED tier. Tile space is scarce; capacity/tile drives max_guests (= 2.2 × total_capacity). Don't churn — every build incurs a 34% asset haircut. Fill empty tiles first; at free_tiles=0 remove the weakest/most-redundant lower-tier ride and place the new tier.
- When a new tier appears in `available_entities`, do this as soon as cash allows — higher tiers generate more revenue. To deploy a higher tier, `place` a new one (or `remove`+`place`).
- Diversification: excitement halves with each duplicate (same subtype + subclass). Vary both.
- Sustained full queue = capacity-bound → add capacity. Add the same ride only while under its saturation cap; at cap, UPGRADE subtype/subclass.

## Learned rules (promoted from prior runs)
Never let num_rides fall to 0: do not remove a ride unless cash covers a replacement ride placed on the same or immediately following step, and if num_rides==0 prioritize placing a ride over any shop modify/wait. (learned ep0)
Prioritise high-tier roller_coaster, ferris_wheel placed instead of existing carousel over new carousel placements once cash allows.
When num_rides is stuck at 1 while shops ≥3 and cash covers a ride's build cost, place a second varied ride (different subtype/subclass) instead of re-modifying shops.