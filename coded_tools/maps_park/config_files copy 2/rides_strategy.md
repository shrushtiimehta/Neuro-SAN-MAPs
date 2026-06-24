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
- At free_tiles=0 or when we have evough research IPs, remove and place the new tier rides, they generate more in revenue.
- Always build the highest UNLOCKED tier. Tile space is scarce; capacity/tile drives max_guests (= 2.2 × total_capacity). Don't churn — every build incurs a 34% asset haircut. Fill empty tiles firs. As soon as tier unlocks, upgrade-in-place at free_tiles=0 by removing the weakest ride. To deploy a higher tier, `place` a new one (or `remove`+`place`).
- Diversification: excitement halves with each duplicate (same subtype + subclass). Vary both.
- Sustained full queue = capacity-bound → add capacity. Add the same ride only while under its saturation cap; at cap, UPGRADE subtype/subclass.

## Learned rules (promoted from prior runs)
- Coaster-for-intensity over redundant yellow: when the fleet is all low-intensity yellow (avg ~1.5) and park_rating is plateaued <=24 with min_uptime=1.0, prefer placing/swapping in a roller_coaster over adding another redundant yellow carousel/ferris; the high-intensity coaster pulls avg_ride_intensity toward 5 and lifts park_rating within 1-2 turns despite the one-turn placement cost. (learned ep0)
- No back-to-back 2nd ferris: do not place a 2nd ferris_wheel on the turn immediately after the 1st; the 2nd identical halves excitement and more than doubles ride_op_cost while the 1st is unproven — wait/modify at least 2 turns and only add a 2nd ferris once the 1st shows a sustained full queue. (learned ep0)
- Yellow->blue swap: once a blue ride subclass is available, REMOVE a redundant yellow ride (3+ of the same yellow subtype on the lot) and place the blue subclass in its slot; the remove itself frees value and the blue placement lifts the all-yellow intensity ceiling. (learned ep0)
- Roller_coaster placement cash/spacing guard: do not place a roller_coaster on a turn where post-placement cash would fall below ~$700 OR a coaster was placed within the prior 3 turns; coaster ride_op_cost spikes immediately and a thin buffer / back-to-back placement turns the placement turn negative. (learned ep1)
- High-op-cost ride cash guard: do not place a high-operating-cost ride (e.g. ferris_wheel) when post-placement cash would fall below ~$300; its per-turn ride_op_cost spikes immediately and a thin cash buffer turns the placement turn negative. (learned ep1)
