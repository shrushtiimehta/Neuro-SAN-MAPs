# Shop Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which shops to place, restock (modify order_quantity), or sell — drink/food/specialty across four tiers (never coordinates). Shops drive recurring revenue and guest happiness; the golden rule is never let a shop run dry, since out-of-service crashes happiness and park_rating.
<!-- PLAYBOOK_SUMMARY:END -->

Only 100 steps per episode — make each a high-impact moves; don't micromanage.

## Shop mechanics (the levers you set)
- **item_cost / item_price** — your per-unit cost / the guest's per-unit price; max_item_price is applied automatically as item_price.
- **order_quantity** — inventory bought at `item_cost` each day start (partial if cash short; unsold spoils at day end). Editable with `modify`.
- **Out of service** — a shop that runs dry mid-day turns guests away and drops happiness + park_rating. Fix it in ONE move: `modify` its `order_quantity` up.

## Shop status readouts (reported per shop, not set by you)
- **inventory** — units left unsold at end of that day; hitting 0 mid-day → out of service, but a large amount still on hand at day close is wasted `item_cost` (it spoils). Tune `order_quantity` so a shop nearly sells out without running dry.
- **revenue_generated** — cumulative sales income for that shop.
- **operating_cost** — the shop's running cost. `revenue_generated - operating_cost` is net contribution — how you should rank shops to cull the worst.
- **uptime** — fraction of the day the shop stayed in service (not dry).

- **Guest spend ceiling** — guests arrive with ~$150; a guest can only buy so much, so revenue past that ceiling comes from more guests or an ATM.
- **Thirst in guests builds ~1.5× faster than hunger.**

## Tier upgrades
- At the start, place low-tier shops, even repeated ones.
- Identical shops (same subtype and tier) add little to the park rating. When available, vary the subtype/tier → more guests → more revenue → more reward. When research unlocks a higher tier (yellow < blue < green < red; see `available_entities`) and cash allows, place it fast.
- If every tile is full (tile space is scarce) and a higher-tier shop needs placing, it costs a two-turn swap — remove the least profitable / most-redundant shop, then place the higher tier next turn.
- Value from a placement earns for the rest of the episode; a step spent idle earns nothing back.

## Specialty shop placement:
- Souvenir pays off wherever many guests pass (high-traffic junctions)
- ATM only changes anything once guests are actually running out of cash — before that it draws nothing.
- Billboard makes guests hungrier/thirstier and routes low-cash guests to an ATM, so its lift only materialises when food shops and an ATM already exist to absorb that extra demand.

## Learned rules (promoted from prior runs)