# All Economics — complete merged reference

Every value below is a simulator constant. Sell-back is 66% of build cost for
rides and shops; ride repair costs 4.5%.

## Rides

| subtype | subclass | building_cost | cost_per_operation | capacity | ticket_price | revenue/run | net/run | runs_to_repay | break_even_days | excitement | intensity | breakdown_rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| carousel | yellow | 250 | 1 | 6 | 4 | 24 | 23 | 11 | 3 | 1 | 1 | 0.001 |
| carousel | blue | 1500 | 2 | 14 | 6 | 84 | 82 | 18 | 4 | 4 | 3 | 0.002 |
| carousel | green | 11500 | 30 | 26 | 14 | 364 | 334 | 34 | 7 | 3 | 4 | 0.003 |
| carousel | red | 24000 | 12 | 24 | 24 | 576 | 564 | 43 | 9 | 8 | 5 | 0.005 |
| ferris_wheel | yellow | 600 | 10 | 10 | 5 | 50 | 40 | 15 | 3 | 2 | 2 | 0.006 |
| ferris_wheel | blue | 7500 | 20 | 20 | 7 | 140 | 120 | 62 | 13 | 5 | 3 | 0.009 |
| ferris_wheel | green | 50000 | 55 | 40 | 15 | 600 | 545 | 92 | 19 | 4 | 6 | 0.024 |
| ferris_wheel | red | 75000 | 75 | 30 | 28 | 840 | 765 | 98 | 20 | 9 | 8 | 0.032 |
| roller_coaster | yellow | 1000 | 8 | 4 | 10 | 40 | 32 | 31 | 7 | 3 | 4 | 0.010 |
| roller_coaster | blue | 18000 | 25 | 12 | 20 | 240 | 215 | 84 | 17 | 7 | 7 | 0.020 |
| roller_coaster | green | 60000 | 45 | 28 | 34 | 952 | 907 | 66 | 14 | 6 | 9 | 0.025 |
| roller_coaster | red | 100000 | 100 | 22 | 50 | 1100 | 1000 | 100 | 20 | 10 | 10 | 0.040 |

ride_rejection_happiness_penalty: 0.2

## Shops

The full `order_quantity` is bought every morning at `item_cost`; unsold stock
is destroyed at close. `margin_per_unit = item_price - item_cost` and
`units_to_repay = building_cost / margin_per_unit`.

| subtype | subclass | building_cost | item_cost | item_price | margin_per_unit | units_to_repay | effects and constants |
|---|---:|---:|---:|---:|---:|---:|---|
| drink | yellow | 100 | 0 | 3 | 3 | 33 | thirst_reduction=0.24 |
| drink | blue | 2250 | 1 | 6 | 5 | 450 | thirst_reduction=0.60 |
| drink | green | 17500 | 3 | 17 | 14 | 1250 | thirst_reduction=0.96; happiness_boost=0.4 |
| drink | red | 48000 | 5 | 25 | 20 | 2400 | thirst_reduction=0.72; energy_boost=20; caffeinated_steps=50 |
| food | yellow | 200 | 1 | 5 | 4 | 50 | hunger_reduction=0.2 |
| food | blue | 3600 | 2 | 9 | 7 | 514 | hunger_reduction=0.5 |
| food | green | 28000 | 4 | 18 | 14 | 2000 | hunger_reduction=0.8; thirst_reduction=0.4 |
| food | red | 60000 | 8 | 34 | 26 | 2308 | hunger_reduction=1.0; happiness_boost=0.6 |
| specialty | yellow | 250 | 4 | 15 | 11 | 23 | happiness_boost=0.5; souvenir shop |
| specialty | blue | 10000 | 2 | 5 | 3 | 3333 | info booth; directs guests to suitable rides |
| specialty | green | 50000 | 3 | 5 | 2 | 25000 | ATM; money_withdrawal=64; min_withdrawal=16 |
| specialty | red | 10000 | 0 | 0 | 0 | never | billboard; thirst_boost=0.25; hunger_boost=0.25; happiness_boost=0.25; money_threshold=25; no direct revenue |

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

Research earns no cash directly.

| speed | days_to_blue_unlock | days_to_green_after_blue_unlock | days_to_red_after_green_unlock | cost_per_day |
|---|---:|---:|---:|---:|
| none | N/A | N/A | N/A | 0 |
| slow | 4 | 8 | 16 | 2000 |
| medium | 2 | 4 | 8 | 8000 |
| fast | 1 | 2 | 4 | 32000 |