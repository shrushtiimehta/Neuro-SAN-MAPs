# Shop Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You decide which shops to place, restock (`modify`), or sell — drink/food/specialty across four tiers (never coordinates). Shops drive recurring revenue and guest happiness; the golden rule is to never let a shop run dry, since out-of-service crashes happiness and park_rating.
<!-- PLAYBOOK_SUMMARY:END -->

**Guests leave** when money, energy, hunger, thirst, or happiness runs critical — and shops cover all five. Guest who leaves early takes their whole remaining spend with them, not just the one sale you missed. Read `shops_economics` to match the shop to the failing need. Also, every GREEN and RED drink/food shop fills a second need on top of the obvious one, so one tile can cover two.
Prefer placing higher tier shops.

## Types of shops:
- **Drink:** quenches thirst. Guests' thirst builds ~1.5× faster than hunger.
- **Food:** satisfies guests’ hunger.
- **Specialty:** unique service per subclass — see `shops_economics`.

## Key attributes:
- **Item cost:** what you pay per unit.
- **Order quantity:** units restocked each morning at `item_cost`; too little cash means partial stocking. Sell out mid-day and the shop goes out of service — it turns guests away, dragging park rating down.
- **Item price:** fixed per subclass (`max_item_price` in `shops_economics`).

## Park current status (not set by you)
- **inventory** — units left unsold.
- **guests_served** — units sold today = popularity. Resets each morning.
- **guests** — park-wide daily averages, incl. `total_guests`, `avg_money_spent` and `avg_time_in_park`.
- **uptime** — fraction of visits that found stock.
- **reachable** — `false` means guests can never walk to that shop, so it earns $0 forever no matter its tier or stock. `remove` it and rebuild on a `reachable_tiles` slot; never `modify` it.
- **next_unlock** — the next tier due and which subtypes still need it, e.g. `{"subtype": "carousel", "tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Absent = research is off. Use to plan ahead.

## `Modify` to set `order_quantity`:
Costs a whole step, so spend one only when a shop's own numbers demand it. Like `uptime` well below 1, or `out_of_service` — shop ran dry then raise `order_quantity` or way too much `inventory` left at close: cut `order_quantity`.

## Tier Upgrade:
- Place a higher tier shop **as soon as** research unlocks it (yellow < blue < green < red; see `available_entities`) and cash allows — higher tiers pay back far more. Each tier has its own distinct benefits, listed in `economics_shops`; read them and exploit them.
- **HOW TO PLACE HIGHER TIERS?** Reachable tiles are scarce, so UPGRADE shops you already have**. Swap ONE shop, over two turns:
  1. `remove` your lowest-tier shop. Tie-break on fewest `guests_served`. Prefer one whose subtype just unlocked.
  2. `place` the new tier on the tile it vacated. Never on an unreachable tile: revenue is always $0.
- Otherwise AVOID `remove`: shop sells back for only 66% of its build cost, so swap only for a genuine tier upgrade. Don't place a shop if you won't need it.

## Learned rules (promoted from prior runs)
In final cash-surplus phases, if reachable shop sites are full and rating is already stable, replace the weakest reachable yellow shop with an unlocked red or green drink shop before ATMs or further basic stock tuning. (learned ep3)
