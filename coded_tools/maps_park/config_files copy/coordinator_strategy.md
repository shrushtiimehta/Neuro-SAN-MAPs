# playbook_coordinator

Strategy_coordinator's rules of thumb: specialist gating, field
ownership, action priority, and always-on safety rules.

## Specialist gating
strategy_coordinator consults these in parallel each turn:
- rides_manager:        always
- park_layout_planner:  always
- shops_manager:        skip only if step < 3
- staffing_manager:     skip if step < 10 AND no broken rides
- research_lead:        skip unless cash ≥ 5000 AND ≥ 1 operational ride;
                        once affordable, consult regardless.

## Field ownership
- rides_manager / shops_manager return subtype/subclass/price (no coords)
- park_layout_planner owns all (x,y) lookups; never guess coordinates

## Action priority order
Applied after FinanceGate. Override the proposer's ranking only when a
higher-priority condition in the snapshot demands it:
0. If no ParkStatus() meaning no rides AND no shops, place a ride. A bare park
   earns nothing, so start building.
1. Broken rides in snapshot -> place mechanic adjacent to the broken ride
2. Shops out of stock -> modify order_quantity
2.5. 2nd janitor: hire when min_cleanliness ≤ 0.80 for 2+ consecutive turns
   AND ≥ 2 rides operational (cleanliness < 0.8 starts a rating penalty;
   janitor is cheap). Full rule in staffing_manager.
3. EARLY RAMP (step ≤ 15): if free_tiles > 0 and an approved place exists,
   prefer it over any ticket-price `modify` - fast capacity funds everything
   downstream. Target ~6-8 rides + 1 drink + 1 food shop by step 15.
4. `wait` is ONLY allowed in the LAST 20 STEPS (step >= 80) - FinanceGate
   REJECTS `wait` before then. Earlier in the run NEVER wait: idle cash
   earns nothing, so deploy the highest-value action that passes FinanceGate
   instead - place/upgrade a ride or shop, start/continue research towards 
   next tier, or restock/re-price a shop.
4. FinanceGate approves the best value action.
5. Reward stalled and root cause unclear -> survey_guests(num_guests=5)

## Safety rules (always)
- Always pass research_topics field for set_research even when speed=none
- ActionDispatcher fires exactly once per turn -- including for 'wait'
- All numeric values in ActionDispatcher args MUST be quoted strings

## Learned rules
