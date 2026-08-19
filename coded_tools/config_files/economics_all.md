# All Economics — every tier, and what it earns

Build costs, price ceilings and the earnings they imply. All figures are the
simulator's own constants; never estimate a number that appears here.
Sell-back is 66% of build cost for any ride or shop; ride repair costs 4.5%.

## Rides
`rev/run` assumes a full ride at `max_price`. `net/run` subtracts `cost_per_op`,
which the sim charges ONLY when the ride actually runs. `runs to repay` is
`build / net-per-run` — how many full runs pay the build cost back.

| subtype | tier | build | cost/op | capacity | max_price | rev/run | net/run | runs to repay | excite | intens | breakdown |
|---|---|---|---|---|---|---|---|---|---|---|---|
| carousel | yellow | 250 | 1 | 6 | 4 | 24 | 23 | 11 | 1 | 1 | 0.001 |
| carousel | blue | 1500 | 2 | 14 | 6 | 84 | 82 | 18 | 4 | 3 | 0.002 |
| carousel | green | 11500 | 30 | 26 | 14 | 364 | 334 | 34 | 3 | 4 | 0.003 |
| carousel | red | 24000 | 12 | 24 | 24 | 576 | 564 | 43 | 8 | 5 | 0.005 |
| ferris_wheel | yellow | 600 | 10 | 10 | 5 | 50 | 40 | 15 | 2 | 2 | 0.006 |
| ferris_wheel | blue | 7500 | 20 | 20 | 7 | 140 | 120 | 62 | 5 | 3 | 0.009 |
| ferris_wheel | green | 50000 | 55 | 40 | 15 | 600 | 545 | 92 | 4 | 6 | 0.024 |
| ferris_wheel | red | 75000 | 75 | 30 | 28 | 840 | 765 | 98 | 9 | 8 | 0.032 |
| roller_coaster | yellow | 1000 | 8 | 4 | 10 | 40 | 32 | 31 | 3 | 4 | 0.01 |
| roller_coaster | blue | 18000 | 25 | 12 | 20 | 240 | 215 | 84 | 7 | 7 | 0.02 |
| roller_coaster | green | 60000 | 45 | 28 | 34 | 952 | 907 | 66 | 6 | 9 | 0.025 |
| roller_coaster | red | 100000 | 100 | 22 | 50 | 1100 | 1000 | 100 | 10 | 10 | 0.04 |

## Shops
`margin` is `max_price - item_cost` per unit sold. `units to repay` is
`build / margin`. You buy the full `order_quantity` every morning and unsold
stock is destroyed at close, so margin only lands on units actually sold.

| subtype | tier | build | item_cost | max_price | margin/unit | units to repay | effect |
|---|---|---|---|---|---|---|---|
| drink | yellow | 100 | 0 | 3 | 3 | 33 | ↓ thirst. |
| drink | blue | 2250 | 1 | 6 | 5 | 450 | ↓ thirst. |
| drink | green | 17500 | 3 | 17 | 14 | 1250 | ↓ thirst and ↑ happiness. |
| drink | red | 48000 | 5 | 25 | 20 | 2400 | ↓ thirst and ↑ energy and walking speed. |
| food | yellow | 200 | 1 | 5 | 4 | 50 | ↓ hunger. |
| food | blue | 3600 | 2 | 9 | 7 | 514 | ↓ hunger. |
| food | green | 28000 | 4 | 18 | 14 | 2000 | ↓ hunger and thirst. |
| food | red | 60000 | 8 | 34 | 26 | 2308 | ↓ hunger and ↑ happiness. |
| specialty | yellow | 250 | 4 | 15 | 11 | 23 | ↑ guest happiness. |
| specialty | blue | 10000 | 2 | 5 | 3 | 3333 | Informs guests about attractions. |
| specialty | green | 50000 | 3 | 5 | 2 | 25000 | Allows guests to withdraw money. |
| specialty | red | 10000 | 0 | 0 | 0 | never | ↑ thirst, hunger, and happiness. |

## Staff
Staff earn nothing — salary is a pure daily cost, paid every day they are hired.
Judge them by the rating damage they prevent, not by revenue.

| subtype | tier | salary/day | effect |
|---|---|---|---|
| janitor | yellow | 25 | Cleans tiles. |
| janitor | blue | 100 | Cleans tiles fast, walks fast. |
| janitor | green | 500 | Cleans tiles faster, walks fast. |
| janitor | red | 2000 | Cleans tiles fastest, walks fast. Provides preventative cleaning. |
| mechanic | yellow | 15 | Repairs rides. |
| mechanic | blue | 100 | Repairs rides fast, walks fast. |
| mechanic | green | 250 | Repairs rides faster, walks fast. |
| mechanic | red | 1000 | Repairs rides fastest, walks fast. Provides preventative maintenance. |
| specialist | yellow | 60 | Entertains guest in ride lines. |
| specialist | blue | 350 | Restocks shops. |
| specialist | green | 250 | Informs guests about dirty or out of service attractions. |
| specialist | red | 300 | Provides fun food and drink to guests waiting in line. |

## Research
Research earns no cash directly; each point spent adds $60 of park value as IP.

| speed | points/day | cost/day | IP value/day |
|---|---|---|---|
| none | 0 | 0 | 0 |
| slow | 25 | 2000 | 1500 |
| medium | 50 | 8000 | 3000 |
| fast | 100 | 32000 | 6000 |

| tier | points to unlock ONE subtype | days slow | days medium | days fast |
|---|---|---|---|---|
| blue | 100 | 4 | 2 | 1 |
| green | 200 | 8 | 4 | 2 |
| red | 400 | 16 | 8 | 4 |

