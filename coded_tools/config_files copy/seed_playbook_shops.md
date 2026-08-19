# Shop Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which shops to place, restock (`modify`), or sell — drink/food/specialty across four tiers (never coordinates). Shops drive recurring revenue and guest happiness; the golden rule is to never let a shop run dry, since out-of-service crashes happiness and park_rating.
<!-- PLAYBOOK_SUMMARY:END -->

**Guests leave** when money, energy, hunger, thirst, or happiness runs critical — and shops cover all five. Read `shops_economics` to match the shop to the failing need: every GREEN and RED drink/food shop fills a second need on top of the obvious one, so one tile can cover two.
Hunger and thirst climb all day while happiness decays, so demand never stops — and a guest who leaves early takes their whole remaining spend with them, not just the one sale you missed. Stop them from leaving.

## Types of shops:
- **Drink:** quenches thirst. Guests' thirst builds ~1.5× faster than hunger, so place drink first when both are missing.
- **Food:** satisfies guests’ hunger.
- **Specialty:** unique service per subclass — see `shops_economics`.

## Key attributes:
- **Item cost:** what you pay per unit.
- **Order quantity:** units restocked each morning at `item_cost`; too little cash means partial stocking. Sell out mid-day and the shop goes out of service — it turns guests away, dragging park rating down.
  - Size it from `total_guests` and for a few days ahead, so you don't burn `modify` actions correcting it.
  - Over-order and the leftover units cost `item_cost` each; run dry and it costs rating. Lean high on yellow/blue, less so on green/red where `item_cost` is steep.
- **Item price:** fixed per subclass (`max_item_price` in `shops_economics`), so reward = `max_item_price - item_cost` is a property of the tier you pick, not something to tune. A tier whose price outruns what guests carry is left holding inventory it already paid for and turns guests away, costing park rating.

## Park current status (not set by you)
- **inventory** — units left unsold.
- **guests_served** — units sold today = popularity. Resets each morning.
- **guests** — park-wide daily averages, incl. `total_guests`, `avg_money_spent` and `avg_time_in_park`.
- **uptime** — fraction of visits that found stock.

## `Modify`:
Sets `order_quantity` — the restock. Omit a field and its current value carries forward.
- Costs a whole step, so spend one only when a shop's own numbers demand it:
  - `uptime` well below 1, or `out_of_service` — ran dry: raise `order_quantity`.
  - `inventory` left at close — never sold out: cut `order_quantity` so you stop paying `item_cost` for units nobody buys.
- Never to fine-tune a shop running clean.

## Tier Upgrade:
- Place a higher tier shop **as soon as** research unlocks it (yellow < blue < green < red; see `available_entities`) and cash allows — higher tiers pay back far more. Each tier has its own distinct benefits, listed in `economics_shops`; read them and exploit them.
- **Every reachable tile taken?** Reachable tiles are scarce, so UPGRADE shops you already have**. Swap ONE shop, over two turns:
  1. `remove` your lowest-tier shop. Tie-break on fewest `guests_served`. Prefer one whose subtype just unlocked.
  2. `place` the new tier on the tile it vacated. Never on an unreachable tile: revenue is always $0.
- Otherwise AVOID `remove`: shop sells back for only 66% of its build cost, so swap only for a genuine tier upgrade. Don't place a shop if you won't need it.

## Let the coordinator know if:
- Guests can't afford your prices — a blue Info Booth keeps them away from what they can't afford and a green ATM gives them more to spend; and for a shop that keeps running dry, ask for a blue Stocker, which refills it mid-day.

## Learned rules (promoted from prior runs)
Skip specialty shops while ride capacity, research, or maintenance actions can still compound returns. (learned ep6)
After drink and food shops are stocked on the main path, add a specialty souvenir shop to the same traffic path without sacrificing essential shop coverage. (learned ep1)
