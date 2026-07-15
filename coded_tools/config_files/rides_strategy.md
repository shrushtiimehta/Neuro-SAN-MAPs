# Rides Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which rides to build, upgrade, or remove — subtype, tier, and ticket price (never coordinates). Rides are the park's main draw and its biggest rating lever: diversify subtypes/tiers, push to higher tiers as research unlocks them, keep them repaired, and never let num_rides hit 0.
<!-- PLAYBOOK_SUMMARY:END -->

## Types of rides:
- **Carousels:** cheapest to build/operate, rarely break, low excitement/capacity.
- **Ferris Wheels:** intermediate, highest capacity of any subtype.
- **Roller Coasters:** expensive, highest excitement/intensity, frequent breakdowns.

## Ride Mechanics
1. **Capacity** — guests per run of the ride. Raising park_rating adds guests only UP TO capacity. To add more guests, increase more ride capacity by building more/higher tier rides. 
2. **Excitement** — raises happiness + rating; ride gains +1 excitement per adjacent water tile.
3. **Intensity** — per-ride score; influences which guests choose it.
4. **Ticket price** — the economics cap (`max_ticket_price` from `economics_rides`) is applied automatically; higher tiers carry a higher cap, so they earn more per guest.
5. **Cost per operation** — deducted each cycle.

## Tier upgrades
- Tile space is scarce: a tile spent on a low tier/basic ride is capacity, excitement, and ticket-cap forgone versus a higher tier/advance ride of the same footprint.
- Higher tiers (yellow < blue < green < red, `available_entities` shows what is unlocked) carry more capacity, excitement, and ticket cap, so placing a newly unlocked tier raises rating, number of guests and revenue, and that gain compounds over the remaining steps.
- When every tile is full, the higher tier costs a two-turn swap - remove the least profitable / most-redundant ride, place the higher tier next turn.
- Value from a placement earns for the rest of the episode; a step spent idle earns nothing back.

## Diversification
Identical attractions (same subtype and tier) give diminishing returns on park_rating; varying subtype and/or tier raises overall rating because guests favour novelty — and higher rating → more guests → more revenue → more cumulative reward. When few tiers are unlocked, spacing duplicates at far location (so guests can pass distinct ones) might recover some of the lost novelty.

## Learned rules (promoted from prior runs)