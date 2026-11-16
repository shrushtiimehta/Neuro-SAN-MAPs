# Frozen Solo Economics

This is the complete economics reference for the two-agent baseline. It is a
checked-in experiment input: launchers and runners must never regenerate or
rewrite it. All numbers are simulator constants. Sell-back is 66% of build cost
for rides and shops; ride repair costs 4.5%.

## Rides

`net/run = ticket_price × capacity - cost_per_operation`.
`runs to repay = building_cost / net/run` at a full load. `break_even_days`
uses the benchmark's five-runs-per-day planning assumption.

| subtype | subclass | building_cost | cost_per_operation | capacity | ticket_price | excitement | intensity | breakdown_rate | runs to repay | break_even_days |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| carousel | yellow | 250 | 1 | 6 | 4 | 1 | 1 | 0.001 | 11 | 3 |
| carousel | blue | 1500 | 2 | 14 | 6 | 4 | 3 | 0.002 | 18 | 4 |
| carousel | green | 11500 | 30 | 26 | 14 | 3 | 4 | 0.003 | 34 | 7 |
| carousel | red | 24000 | 12 | 24 | 24 | 8 | 5 | 0.005 | 43 | 9 |
| ferris_wheel | yellow | 600 | 10 | 10 | 5 | 2 | 2 | 0.006 | 15 | 3 |
| ferris_wheel | blue | 7500 | 20 | 20 | 7 | 5 | 3 | 0.009 | 62 | 13 |
| ferris_wheel | green | 50000 | 55 | 40 | 15 | 4 | 6 | 0.024 | 92 | 19 |
| ferris_wheel | red | 75000 | 75 | 30 | 28 | 9 | 8 | 0.032 | 98 | 20 |
| roller_coaster | yellow | 1000 | 8 | 4 | 10 | 3 | 4 | 0.010 | 31 | 7 |
| roller_coaster | blue | 18000 | 25 | 12 | 20 | 7 | 7 | 0.020 | 84 | 17 |
| roller_coaster | green | 60000 | 45 | 28 | 34 | 6 | 9 | 0.025 | 66 | 14 |
| roller_coaster | red | 100000 | 100 | 22 | 50 | 10 | 10 | 0.040 | 100 | 20 |

ride_rejection_happiness_penalty: 0.2

## Shops

The full `order_quantity` is bought every morning at `item_cost`; unsold stock
is destroyed at close. `units_to_repay = building_cost / (item_price - item_cost)`.

| subtype | subclass | building_cost | item_cost | item_price | units_to_repay | effects and constants |
|---|---:|---:|---:|---:|---:|---|
| drink | yellow | 100 | 0 | 3 | 33 | thirst_reduction=0.24 |
| drink | blue | 2250 | 1 | 6 | 450 | thirst_reduction=0.60 |
| drink | green | 17500 | 3 | 17 | 1250 | thirst_reduction=0.96; happiness_boost=0.4 |
| drink | red | 48000 | 5 | 25 | 2400 | thirst_reduction=0.72; energy_boost=20; caffeinated_steps=50 |
| food | yellow | 200 | 1 | 5 | 50 | hunger_reduction=0.2 |
| food | blue | 3600 | 2 | 9 | 514 | hunger_reduction=0.5 |
| food | green | 28000 | 4 | 18 | 2000 | hunger_reduction=0.8; thirst_reduction=0.4 |
| food | red | 60000 | 8 | 34 | 2308 | hunger_reduction=1.0; happiness_boost=0.6 |
| specialty | yellow | 250 | 4 | 15 | 23 | happiness_boost=0.5; souvenir shop |
| specialty | blue | 10000 | 2 | 5 | 3333 | info booth; directs guests to suitable rides |
| specialty | green | 50000 | 3 | 5 | 25000 | ATM; money_withdrawal=64; min_withdrawal=16 |
| specialty | red | 10000 | 0 | 0 | never | billboard; thirst_boost=0.25; hunger_boost=0.25; happiness_boost=0.25; money_threshold=25; no direct revenue |

specialty_decay_rate: 2

## Staff

Staff produce no direct revenue. Salary is charged every hired day.

| subtype | subclass | salary | operational constants and effect |
|---|---:|---:|---|
| janitor | yellow | 25 | clean_rate=0.028; cleaning_threshold=0.85 |
| janitor | blue | 100 | clean_rate=0.075; cleaning_threshold=0.95; fast walking |
| janitor | green | 500 | clean_rate=0.2; cleaning_threshold=1.0; fast walking |
| janitor | red | 2000 | clean_rate=0.35; cleaning_threshold=1.2; preventative cleaning |
| mechanic | yellow | 15 | repair_rate=2 |
| mechanic | blue | 100 | repair_rate=8; fast walking |
| mechanic | green | 250 | repair_rate=20; fast walking |
| mechanic | red | 1000 | repair_rate=50; preventative maintenance |
| specialist | yellow | 60 | clown; happiness_boost=0.25 |
| specialist | blue | 350 | stocker; stocking_rate=0.1; max_inventory=100; restock_threshold=0.25; idle_ticks=30 |
| specialist | green | 250 | park crier; warns about dirty/out-of-service attractions |
| specialist | red | 300 | vendor; happiness_boost=0.2; hunger_reduction=0.3; thirst_reduction=0.4 |

## Research

Research earns no cash directly. Each research point adds $60 of park value as IP.

| speed | speed_progress | speed_cost | IP_value_per_day |
|---|---:|---:|---:|
| none | 0 | 0 | 0 |
| slow | 25 | 2000 | 1500 |
| medium | 50 | 8000 | 3000 |
| fast | 100 | 32000 | 6000 |

| tier | points_required | days_slow | days_medium | days_fast |
|---|---:|---:|---:|---:|
| blue | 100 | 4 | 2 | 1 |
| green | 200 | 8 | 4 | 2 |
| red | 400 | 16 | 8 | 4 |

`speed_progress` is the number of research points added per game day, and `speed_cost` is the cash charged on each game day that research runs. If the park cannot pay the daily cost, research stops and `research_speed` becomes `none`.

The `days_slow`, `days_medium`, and `days_fast` columns show the uninterrupted, fully funded game days required to unlock that tier for **one subtype** at the corresponding speed. Each value is calculated as `points_required / speed_progress`. Tiers unlock sequentially (yellow → blue → green → red), and the table is not cumulative. For example, after blue carousel is unlocked, green carousel requires 200 additional points: 8 slow days, 4 medium days, or 2 fast days. Taking one subtype from yellow through red requires 700 total points: 28 slow days, 14 medium days, or 7 fast days.

When multiple research topics are selected, the simulator moves to the next selected subtype after each tier unlock. A particular subtype can therefore take longer to reach green or red than the table suggests. Select only one topic to advance that subtype through its tiers as quickly as possible.
