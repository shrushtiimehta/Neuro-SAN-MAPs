# rides_manager - policy

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary (regenerated every episode)
Build fast early: reach ~6 rides by turn 20 and ~12 by turn 34 (carousel, ferris_wheel, roller_coaster) as last ep did. Rides are the guest-draw base, not the per-step reward engine - do not keep placing rides in the mid/late game at the expense of shop modifies. Remove clearly weak/low-draw carousels when a slot is better used (last ep removals at 46/62 each paid >900). Verify a tile is free before placing to avoid path-collision rejections (step-60 fail).
<!-- PLAYBOOK_SUMMARY:END -->

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
- Tile space is scarce, so capacity per tile matters. Don't churn — every build/remove incurs a 34% asset haircut. Remove the weakest/most-redundant lower-tier ride and to place higher tier rides.
- Higher tiers exist for a reason — blue/green/red bring substantially more capacity, excitement, and ticket price than yellow. Make a point of placing them whenever cash and tile space allow; DON'T get stuck on an all-yellow fleet.
- Diversification: identical rides (same ride and tier) give diminishing returns on park rating. ALWAYS vary the ride and/or tier when options allow. When too few are unlocked to vary, don't place duplicates back-to-back — place them several steps apart.
- Sustained full queue = capacity-bound → add capacity. Add the same ride only while under its saturation cap; at cap, UPGRADE subtype/subclass.

## How you move park_rating (status carries `park_rating`)
Rides are the biggest positive lever and also two of the things that can drag rating down:
- **Excitement:** higher excitement raises guest happiness and park rating, and higher tiers carry more excitement. Identical rides (same subtype AND tier) give diminishing returns — diversify subtype and tier to keep the gains; an all-yellow-carousel fleet barely moves rating.
- **Intensity:** keep the fleet's AVERAGE intensity near 5. An all-coaster park (too high) or an all-carousel park (too low) both lower rating.
- **Breakdowns:** a broken ride is out of service — frequent out-of-service rides lower rating and turn guests away. Coasters break most; keep a mechanic and don't let `broken_rides` linger. A sudden `park_rating` drop usually means a fresh breakdown.

## Learned rules (promoted from prior runs)
Once research unlocks a higher ride tier, add the highest available non-yellow subclass rides (removing older yellow ones) so the non-yellow fleet count grows through the back half. (learned ep5)
Once a non-yellow ride tier unlocks, churn the fleet upward by removing the weakest yellow rides and replacing them with the highest available tier instead of placing more yellows. (learned ep0)
Never let num_rides fall to 0: do not remove a ride unless cash covers a replacement ride placed on the same or immediately following step, and if num_rides==0 prioritize placing a ride over any shop modify/wait. (learned ep0)
Prioritise high-tier roller_coaster, ferris_wheel placed instead of existing carousel over new carousel placements once cash allows.
When num_rides is stuck at 1 while shops ≥3 and cash covers a ride's build cost, place a second varied ride (different subtype/subclass) instead of re-modifying shops.