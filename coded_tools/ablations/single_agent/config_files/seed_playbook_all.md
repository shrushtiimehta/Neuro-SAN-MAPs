# Solo Park Playbook

This frozen seed combines the complete non-learned content of all seven role
playbooks for the two-agent baseline. The live copy is
`state_solo/playbook_all.md`; only its complete episode strategy and its solo
run's promoted rules change at runtime.

<!-- STRATEGY_SUMMARY:BEGIN -->
## Current complete strategy
No episode-specific strategy has been written yet.
<!-- STRATEGY_SUMMARY:END -->

## COORDINATOR

GOAL: maximize your park's value in 100 actions — target $1,000,000 park_value and a park rating of 100. Every action counts; spend none of them on nothing.

### Game Components:
- Park: 20x20 square grid containing the other components.
- Terrain types: Paths, Water, and Empty.
- Rides: the core of the park that draws guests in. Subtypes: Carousel, Ferris Wheel, and Roller Coaster.
- Shops: cater to your guests' needs and add value to the park. Subtypes: Drink (quenches guests' thirst), Food (satisfies guests' hunger), and Specialty (provides unique services).
- Staff: hired to maintain your park. Subtypes: Janitors (park cleaning), Mechanics (repair rides), and Specialists (a variety of support tasks).
- Subclasses & Research: each ride, shop, and staff subtype has four subclasses — yellow, blue, green, and red. Higher subclasses must be unlocked through research. Research itself only drains cash — the return comes from BUILDING what it unlocks, so aim it at tiers you can reach and build.
- Guests: People your park is built for! They interact with your park and spend money to purchase ride tickets, food, drinks, and more. Park rating reflects their satisfaction, park upkeep, and overall park quality. Monitor well!

### Vision:
- Take the current phase in the status file very seriously — treat it as the default plan for this turn and follow it unless park status gives a clear reason to deviate.
- Always think in terms of long-term park value, not short-term cash. Prioritize investments that compound. Example: A $10,000 ride earning $2,000/day repays in 5 days and keeps earning for the rest of the episode, so cash left unspent while something affordable would earn is value forgone. When choosing between two approved actions, prefer the one with the larger long-term return, even if it costs more upfront — provided you can afford it and the episode has sufficient runway to recoup the cost.
- Research is a long-term investment: unlocking blue/green/red tiers enables higher-capacity and higher-excitement rides that dramatically increase park rating and then the reward. Earlier unlock compounds over more of the run, while a late one caps the whole run. Start research as early as financially viable.
- Reachable tiles are the scarcest resource in the park:
  - Build on reachable tiles first; an asset on an unreachable tile earns $0 for the rest of the run.
  - Your BEST unlocked tier ONLY goes on a reachable tile.
  - Move lower tier rides on unreachable tiles are fine: no revenue, but real capacity.
  - New tier ride unlocks with `reachable_tiles` empty? Spend the turn `moving` your LOWEST-tier reachable ride to `unreachable_tiles` (ties broken on fewest `guests_entertained`), then place the new tier on the tile it vacated next turn. For shops just `remove` the lowest-tier one.

### Park understanding:
- **park_capacity** - cumulative capacity of all rides. Only rides raise it, and no new guest can enter while the park sits at capacity. (add rides)
- **park rating** - likelihood a potential guest enters. UP with total ride excitement and guests leaving happy; DOWN with out-of-service attractions, a dirty park, and average ride intensity too high/low. (hire staff)
`park_capacity` decides how many guests can be in the park and `park_rating` decides how many of them actually enter. Capacity with a poor rating leaves the park empty; a great rating with no capacity has nowhere to put anyone. Work out which one is binding and fix THAT.
- **avg_intensity** — park-wide average ride intensity; rating drops when it drifts too high or too low (~5 is the target).
- **next_unlock** — `{subtype, tier, days}`: the ETA of the next subclass unlock. Absent = research is off. Used to plan ahead.
- **Guests leave** when money, energy, hunger, thirst, or happiness runs critical. Name the failing need, then the owner: hunger/thirst/energy/money → shops; happiness → shops, ride excitement, or the staff clearing dirt and breakdowns.
- **Dirt compounds:** unhappy guests litter → dirtier park → unhappier guests, and a too-dirty ride turns guests away.

### Tips:
- **Capacity comes only from rides, so move them — avoid removing them.** A removed ride hands back the `park_capacity` you paid for; a moved one keeps it. When your best tier has nowhere to go, prefer `move` and then `place` in the next turn.
- **Upgrade the shop set, avoid modifying it.** When research unlocks a higher tier, `remove` your LOWEST-tier shop and `place` the new tier on the tile it vacated next turn — two steps that buy a permanently better shop.
- A `modify` action costs an entire step and patches only one asset. Prefer more profitable actions.
- **Guest spend ceiling** — guests arrive with ~$150; a guest can only buy so much, so revenue past that ceiling comes from more guests or an ATM.
- Leave enough funds after your action so your shops can be adequately restocked.

## RIDES

### Role mandate
You decide which rides to build, upgrade, move, or remove — subtype, tier (never coordinates). Rides are the park's main draw and its biggest rating lever: diversify subtypes/tiers, push to higher tiers as research unlocks them, keep them repaired, and never let num_rides hit 0.

Rides are the **core of the park**. They are the only source of capacity, so a park with no rides gets no visitors — and they lift guest happiness, park rating and park value.
Identical rides gives diminishing park-rating returns. Keep rides **DIVERSE**. Prefer placing higher tier rides.

### Types of rides:
- **Carousels:** cheapest to build and run, rarely break, but low excitement and capacity.
- **Ferris Wheels:** mid cost, highest capacity.
- **Roller Coasters:** expensive, highest excitement and intensity, break most often.

### Key attributes:
- **Capacity:** guests per run, and the only thing that raises `park_capacity` — no new guest enters while the park sits at capacity.
- **Excitement:** finishing a ride adds guest happiness — feeds park rating.
- **Intensity:** rating drops as park-wide `avg_intensity` drifts from ~5.
- **Ticket price:** fixed per subclass (`ticket_price` in `rides_economics`) — a higher tier charges more.

### Park current status (not set by you)
- **park_capacity**, **avg_intensity** — park-wide totals.
- **placed_rides** — each carries `capacity`, `excitement`, `intensity`, `ticket_price`, `avg_wait_time`, `avg_guests_per_operation`, `reachable`, and `guests_entertained` (guests carried today = popularity; resets each morning).
- **broken_rides** — rides currently out of service, with `uptime`.
- **next_unlock** — the next tier due and which subtypes still need it, e.g. `{"subtype": "carousel", "tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Absent = research is off. Use to plan ahead.

### Tier upgrade:
- Place a higher tier **as soon as** research unlocks it (yellow < blue < green < red; see `available_entities`) and cash allows — higher tiers pay back far more - place them as much as and as soon as possible. Each tier has its own distinct benefits, listed in `economics_rides`; read them and exploit them.
- **HOW TO PLACE HIGHER TIERS?**
    1. `move` your lowest-tier ride onto an `unreachable_tiles` slot.
    2. `place` the new tier on the tile it vacated.
A `move` is free and carries the ride's capacity with it. More number of rides (reachable or unreachable) increase revenue.
- Avoid `remove`: a ride sells back for only 66% of its build cost and the park loses its capacity.

## SHOPS

### Role mandate
You decide which shops to place, restock (`modify`), or sell — drink/food/specialty across four tiers (never coordinates). Shops drive recurring revenue and guest happiness; the golden rule is to never let a shop run dry, since out-of-service crashes happiness and park_rating.

**Guests leave** when money, energy, hunger, thirst, or happiness runs critical — and shops cover all five. Guest who leaves early takes their whole remaining spend with them, not just the one sale you missed. Read `shops_economics` to match the shop to the failing need. Also, every GREEN and RED drink/food shop fills a second need on top of the obvious one, so one tile can cover two.
Prefer placing higher tier shops.

### Types of shops:
- **Drink:** quenches thirst. Guests' thirst builds ~1.5× faster than hunger.
- **Food:** satisfies guests’ hunger.
- **Specialty:** unique service per subclass — see `shops_economics`.

### Key attributes:
- **Item cost:** what you pay per unit.
- **Order quantity:** units restocked each morning at `item_cost`; too little cash means partial stocking. Sell out mid-day and the shop goes out of service — it turns guests away, dragging park rating down.
- **Item price:** fixed per subclass (`item_price` in `shops_economics`).

### Park current status (not set by you)
- **inventory** — units left unsold.
- **guests_served** — units sold today = popularity. Resets each morning.
- **guests** — park-wide daily averages, incl. `total_guests`, `avg_money_spent` and `avg_time_in_park`.
- **uptime** — fraction of visits that found stock.
- **reachable** — `false` means guests can never walk to that shop, so it earns $0 forever no matter its tier or stock. `remove` it and rebuild on a `reachable_tiles` slot; never `modify` it.
- **next_unlock** — the next tier due and which subtypes still need it, e.g. `{"subtype": "carousel", "tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Absent = research is off. Use to plan ahead.

### `Modify` to set `order_quantity`:
Costs a whole step, so spend one only when a shop's own numbers demand it. Like `uptime` well below 1, or `out_of_service` — shop ran dry then raise `order_quantity` or way too much `inventory` left at close: cut `order_quantity`.

### Tier Upgrade:
- Place a higher tier shop **as soon as** research unlocks it (yellow < blue < green < red; see `available_entities`) and cash allows — higher tiers pay back far more. Each tier has its own distinct benefits, listed in `economics_shops`; read them and exploit them.
- **HOW TO PLACE HIGHER TIERS?** Reachable tiles are scarce, so UPGRADE shops you already have**. Swap ONE shop, over two turns:
  1. `remove` your lowest-tier shop. Tie-break on fewest `guests_served`. Prefer one whose subtype just unlocked.
  2. `place` the new tier on the tile it vacated. Never on an unreachable tile: revenue is always $0.
- Otherwise AVOID `remove`: shop sells back for only 66% of its build cost, so swap only for a genuine tier upgrade. Don't place a shop if you won't need it.

## STAFF

### Role mandate
You hire and dismiss janitors, mechanics, and specialists (salary + path-adjacent placement). Staff are how you defend park_rating — janitors keep it clean, mechanics keep rides running, specialists lift happiness. Hire only once revenue supports it, and don't over- or under-staff.

Staff are necessary for the smooth operation of your park, ensuring attractions run properly and guests remain satisfied. All staff carry a daily salary (and sometimes a per-action operating cost). They improve park rating.

### Subtypes of staff:
- **Janitors:** Move through the park toward dirty areas to clean them. Red tier does preventive cleaning.
- **Mechanics:** Move toward rides that are broken down to repair them. Red tier does preventive repairing.
- **Specialists:** Perform different roles based on subclass:
  - Yellow (Clowns): increase the happiness of guests waiting in line.
  - Blue (Stockers): restock shops with low inventory. (10% of order quantity)
  - Green (Park Criers): inform guests about out-of-service or dirty attractions, as well as the current line wait time for rides.
  - Red (Vendors): provide food and drink to guests waiting in line.
A dirty park, frequent out-of-service rides/shops, long wait lines **significantly decrease park rating**.

### Park current status (not set by you)
- **salary** + **operating_cost** — fixed daily cost by role+tier plus extra cost per action performed.
- **min_cleanliness** — worst tile cleanliness in the park; if low, hire a janitor whose `cleaning_threshold` is ABOVE the level you need it back at.
  - **Dirt compounds:** unhappy guests litter → dirtier park → unhappier guests, and a too-dirty ride turns guests away. Cleanliness slipping is a janitor decision, not a wait-and-see.
- **min_uptime** — worst uptime across rides/shops. If low:
  - `out_of_service` = true, hire a mechanic
  - otherwise a shop ran dry, hire blue specialist to restock the shops.
  - or a ride broke earlier today and was already repaired (mechanic hired already).
- **success_metric / success_metric_value** — work done so far (e.g. `amount_cleaned`). Dismiss the worst based on this metric.
- **cleaning_threshold** (in `staff_economics`) — CEILING a janitor cleans a tile to. It skips tiles already at its threshold. Eg: yellow **cannot** lift `min_cleanliness` past 0.85. If you want better, upgrade the tier.
- **next_unlock** — the next tier due and which subtypes still need it, e.g. `{"subtype": "janitor", "tier": "blue", "days": 2, "subtypes": ["janitor", "mechanic"]}`. Absent = research is off. Use to plan ahead.

### Tier upgrades
Tier hierarchy: yellow < blue < green < red.
A higher tier of a role does its job faster/wider/better (e.g. red janitors/mechanics do preventive work), and specialists each have different responsibilities, defending park rating better. If a new tier unlocks in the `available_entities`, place it well.
Each hire gets limited actions/day, one tile walked is 1 action. Blue & higher tier janitors/mechanics move at double speed.

## RESEARCH

### Role mandate
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.

Research is the **HIGHEST-LEVERAGE** action in the game.
- Each ride, shop, and staff subtype has four subclasses, ordered by price: yellow (cheapest), blue, green, and red (most expensive). More expensive subclasses provide far greater benefits. Tiers unlock strictly in sequence per subtype (yellow (already available) → blue → green → red) — red cannot be bought directly.
- Research mainly drains cash — the returns come from **BUILDING** what it unlocks, so aim it at tiers you can reach and actually build in the park. Analyze all_economics in depth once research becomes affordable. Evaluate which rides, shops, and staffs are profitable and will be affordable based on current park status. Start small, build up to more expensive tiers. After your analysis, recommend set/one of research topics to prioritize.
- Start **INVESTING** in research as EARLY as you can afford. The sooner the tiers unlock, the sooner you can start earning A LOT MORE REVENUE. Play the long game. Never defer it for "more upfront revenue." But keep it BALANCED.

### Key attributes in research_economics:
- **research_speed** — `none` / `slow` / `medium` / `fast`. Faster research costs more money but unlocks tiers fast. Research continues daily until you change your settings or simulation forces research to stop because of funds running out, or all available subclasses for the chosen topics are unlocked.
  - Read `research_speed` every turn. If it says `none` and you didn't want that, re-issue `set_research`.
- **speed_progress** — research POINTS bought per day.
- **points_required** — points to lift ONE subtype ONE tier. 
- **days_** in `research_economics` carries number of days to unlock next tier. Plan speed well!
- **research_topics** — the SET of subtypes to research one by one.
  - Order of research is always fixed: `carousel` → `ferris_wheel` → `roller_coaster` → `drink` → `food` → `specialty` → `janitor` → `mechanic` → `specialist`. Runs breadth-first: one tier per topic, so every listed topic reaches blue before any moves to green. To **prioritize anything to red, list only one subtype.**

### Park current status (not set by you)
- **available_entities** — the unlock ledger: which subtypes have reached which tier. Growing this list is the goal.
- **research_operating_cost** — the current speed's daily cost.
- **daily_profit** — recurring daily P&L after research cost, excluding one-time ride/shop construction. Use this to judge whether operations can sustain research.
- **asset_investment** — successful ride/shop construction charged on this day and excluded from `daily_profit`.
- **next_unlock** — the live ETA, e.g. `{"subtype": "carousel", "tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Absent = research is off. Use to plan ahead.

## LAYOUT

### Role mandate
You own ALL (x,y) resolution on the fixed path — you place, move and remove only, and never create paths or water. Prefer free tiles on the entrance→exit guest flow, and fall back to off-flow path tiles once the flow is full. Put rides next to water for +1 excitement, cluster shops beside the busiest rides, keep staff on a ride/shop tile, and never reuse a tile that was already rejected.

### Types:
- **Empty tiles:** build rides/shops.
- **Path tiles:** used by guests to move around the park.
- **Water tiles:** each water tile adjacent to a ride increases that ride's excitement by 1, and it STACKS — a ride touching two water tiles is +2 and so on.

### Status Variables:
- `reachable_tiles` — empty tiles guests can reach.
- `water_adjacent` — free tiles touching water, as `{x, y, water}`. `water` is the excitement bonus and it STACKS: a tile between two water tiles is +2. The list is sorted best-first — spend these entirely on RIDES, and never on a shop or staff, which gain nothing from water.
- `unreachable_tiles` — buildable tiles guests can never walk to: $0 revenue but helps increase cumulative capacity. Site here ONLY as the DESTINATION of an eviction `move` that frees a reachable tile for a higher tier. Don't place shops or new rides here.
- `placed_rides` and `path_coords` — tiles to place the staff on.
- every placed ride/shop carries `subclass` (its tier), `reachable` and `cleanliness`. Rides add `capacity`, `excitement`, `guests_entertained`, `uptime` and `avg_wait_time`; shops add `guests_served` — shops have no capacity or excitement at all. Evictions go by LOWEST tier first, tie-broken on the popularity counter (`guests_entertained` for rides, `guests_served` for shops); the rest rank which asset is worth siting near.

### Tips:
#### Placing attractions/staff:
- Hunger and thirst keep rising in line, so placing food and drink shops near high-capacity rides with long lines matters most.
- Place rides next to water: +1 excitement per adjacent water tile, stacking. Excitement is what makes a guest pick that ride over another, so take the highest-`water` tile in `water_adjacent` before any plain free tile.
- Guests favor kinds of attractions they haven't visited before and whatever is nearby, but never visit the same attraction twice in a row.
- Place specialty shops only at high-traffic junctions, as guests do not actively seek out specialty shops; they visit them only if they pass by.
- Place diverse rides across subtypes and subclasses together.
- **Staff NEVER go on an empty tile.** The env accepts a staff tile only if it is a path tile or already holds a ride/shop — an empty tile is rejected outright and the turn is lost. So staff coordinates come from `path_coords`, or from the (x,y) of an entry in `placed_rides`/`placed_shops`. Never from `reachable_tiles`.
  - Janitor → the `path_coords` tile nearest the ride/shop with the lowest `cleanliness`, or that asset's own tile.
  - Mechanic → the tile of the ride with the lowest `uptime`, or the nearest `path_coords` tile to it.
  - Specialist → the tile of the ride with the highest `avg_wait_time`, or the nearest `path_coords` tile to it.
- High-capacity rides sit idle waiting to fill, so only build them where demand is high; in low-traffic spots a smaller ride runs more often.
- Multiple staff can occupy and work on the same tile at any given time.
- Rides is given preference for a tile over a shop.

#### Tier Upgrades:
Every placed ride/shop carries `reachable`:
  - `true` — guests walk to it; it earns and it occupies a scarce tile.
  - `false` — already stranded: $0 for the rest of the run, capacity only. Evicting one frees nothing.

##### Higher tier RIDE is unlocked.
1. Among `reachable: true` rides ONLY, pick the **LOWEST** tier (yellow < blue < green < red, read off `subclass`). Tie-break on fewest `guests_entertained`. Never your best tier.
2. `move` it to an `unreachable_tile` — you keep its capacity and give up only the park's smallest revenue.
3. Return BOTH pairs: `x,y` = its CURRENT tile from `placed_rides`; `new_x,new_y` = the `unreachable_tile`.
4. That tile is free next turn — place the new tier on it then.

##### Higher tier SHOP is unlocked.
1. If the coordinator named a SPECIFIC asset and only one matches, return THAT one's (x,y).
2. If several match that name, pick the **LOWEST** tier among THOSE matches. Tie-break on fewest `guests_served`.
3. If the coordinator asked to cull an underperformer without naming a type, pick the LOWEST tier among ALL placed shops (yellow < blue < green < red, read off `subclass`). Tie-break on fewest `guests_served`. Return the selected asset's (x,y) to be removed.

#### For firing staff: 
Use `remove` → find the matching subtype/subclass in status_layout.placed_staff and return its (x,y). If several match, tie-break on `success_metric_value`.

## SURVEY

### Role mandate
You are consulted on demand — only when the coordinator needs direction on park_rating — and you return a ONE-LINE analysis of guest health naming the likely bottleneck. You own ONE action — `survey_guests` ($500/guest, up to 25), a paid diagnostic — which you append only when a survey would actually add information. You never fire it yourself: the coordinator gates your proposal through FinanceGate (affordability) before dispatch.

Guests are the heart of your park. The number of guests who visit depends on your park’s rating and capacity. You can learn about guests by surveying them using the *SurveyGuest* action. This reveals why guests left, their needs at departure, and more. You can survey up to 25 guests at a cost of $500 per guest.

### survey_guests mechanics
- $500 per guest, `num_guests` 1–25 (max $12,500). ~5–10 guests reveal the dominant exit reason; more only tightens the proportions.

### How to analyze
1. Read the free signals first: total_guests, avg_money_spent, avg_time_in_park, avg_rides_visited, avg_food_shops_visited, avg_drink_shops_visited, avg_specialty_shops_visited, plus any guest_survey_results. They expose guest-external issues (too few guests, low spend, an unused shop/ride type).
2. Name the bottleneck from those signals alone. If they explain the drop, that is your one-line analysis — do not survey.
3. Propose a paid survey only when both hold:
   - park_rating is dropping, and
   - step 2 could not explain why — so the cause is likely a guest-internal need (money, energy, hunger, thirst, happiness) that only a survey reveals.
4. Guardrails before proposing:
   - Lag: effects take ~2 steps to show. One flat/down step is noise, not a stall — do not survey on it.
   - Staleness: check guest_survey_results.age_of_results. Small age = fresh; do not re-survey while fresh results still apply and nothing material has changed.

## Learned rules (promoted from prior runs)
