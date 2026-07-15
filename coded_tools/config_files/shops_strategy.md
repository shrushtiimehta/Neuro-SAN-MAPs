# Shop Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which shops to place, restock (modify order_quantity), or sell — drink/food/specialty across four tiers (never coordinates). Shops drive recurring revenue and guest happiness; the golden rule is never let a shop run dry, since out-of-service crashes happiness and park_rating.
<!-- PLAYBOOK_SUMMARY:END -->

## Shop types (all have 4 tiers: yellow < blue < green < red)
- **Drink** (higher tier = higher price cap): quenches thirst — green reduces it most. Green also boosts happiness; red — boosts energy and lets guests move twice as fast.
- **Food** (higher tier = more hunger reduction + higher price cap): satisfies hunger. Green tier also quenches thirst; red tier gives an extra happiness boost.
- **Specialty**:
  - yellow = Souvenir: boosts happiness.
  - blue = Info Booth: informs guests about attractions/prices so they only visit rides within their budget and preferences.
  - green = ATM: lets guests withdraw cash to spend.
  - red = Billboard: earns $0 direct revenue, makes guests hungrier/thirstier/happier, guests revisit more, and sends guests with <$25 to an ATM.
  - Specialty timing/dependencies: a Souvenir pays off wherever many guests pass (high-traffic junctions). An ATM only changes anything once guests are actually running out of cash — before that it draws nothing. A Billboard makes guests hungrier/thirstier and routes low-cash guests to an ATM, so its lift only materialises when food and an ATM already exist to absorb that extra demand.

## Shop mechanics
- **order_quantity** — inventory bought at `item_cost` each day start (partial if cash short; unsold spoils). `modify` any near-empty `placed_shops` entry to a larger `order_quantity`.
- **Out of service** — a shop that runs dry mid-day turns guests away and drops happiness + park_rating, so inventory (`order_quantity`) is the most direct rating lever a shop has; a `modify` raising a near-empty `placed_shops` entry's `order_quantity` refills it.
- **item_cost / item_price** — your per-unit cost / the guest's per-unit price; the price cap (`max_item_price`) is applied automatically, and higher tiers carry a higher cap.
- **Thirst outpaces hunger** — thirst builds ~1.5× faster than hunger.
- **Guest spend ceiling** — guests arrive with ~$150; a guest can only buy so much, so revenue past that ceiling comes from more guests or an ATM.

## Tier upgrades
- Tile space is scarce (`available_entities` shows what is unlocked): a tile on a low tier is price-cap and effect forgone versus a higher tier of the same footprint.
- Placing a newly unlocked higher tier raises revenue and rating, and that compounds over the remaining steps. When every tile is full, the higher tier (or a diverse new shop) costs a two-turn swap — remove the least profitable shop (lowest `revenue_generated` in `placed_shops`) or the most redundant one, place the replacement next turn — so the replacement has to beat what it displaced.
- Value from a placement earns for the rest of the episode; a step spent idle earns nothing back.

## Diversification
Identical shops (same subtype and tier) give diminishing returns on park_rating; varying subtype and/or tier raises overall rating because guests favour novelty — and higher rating → more guests → more revenue → more cumulative reward. When few tiers are unlocked, spacing duplicates at far location (so guests can pass distinct ones) might recover some of the lost novelty.

## Learned rules (promoted from prior runs)