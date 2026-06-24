# playbook

This is the live strategy document for the maps_park agent network.
Anthropologist owns the writes; every other agent reads it at the start
of its call and follows the relevant section. When a hypothesis is
confirmed at episode end, trial_analyst folds the new rule into the
appropriate section here (rather than keeping a separate rules file).

---

## Action priority order
Applied by action_gatekeeper after FinanceGate. Override the proposer's
ranking only when a higher-priority condition in the snapshot demands it:
1. Broken rides in snapshot -> place mechanic adjacent to the broken ride
2. Shops out of stock -> modify order_quantity
3. Park is bare (no rides AND no shops) -> first ride placement
4. Best approved proposal from FinanceGate
5. Reward stalled and root cause unclear -> survey_guests(num_guests=5)
6. Otherwise -> wait

## Specialist gating
strategy_coordinator consults these in parallel each turn:
- rides_manager:        always
- park_layout_planner:  always
- shops_manager:        skip only if step < 3
- staffing_manager:     skip if step < 10 AND no broken rides
- research_lead:        skip if step < 20 OR cash < 6000

rides_manager/shops_manager return subtype/subclass/price (no coords).
park_layout_planner owns all (x,y) lookups. Never guess coordinates.

## Research priority
1. carousel or ferris_wheel  unlock blue tier first for capacity
2. roller_coaster            only after blue rides placed and profitable
3. drink/food shops          once ride revenue is stable
4. staff                     lowest priority; yellow staff covers early game

Research safety: do not propose research unless cash covers 3+ days of
the proposed speed_cost without dipping below daily recurring costs.

## Default episode checklist (when no prior signal)
- turns 1-5:    place first ride and drink shop, establish guest flow
- turns 5-15:   optimise ticket prices, add food shop
- turns 15-30:  hire first janitor, monitor cleanliness
- turns 30-50:  start slow research toward blue tier rides
- turns 50-70:  place blue ride(s), expand shop capacity
- turns 70-100: maximise park value, sell loss-making assets

Anthropologist may use more phases (10-15+) when context suggests it.

## Safety rules (always)
- price arg for any ride placement MUST equal max_ticket_price exactly
- Always pass research_topics field for set_research even when speed=none
- ActionDispatcher fires exactly once per turn -- including for 'wait'
- All numeric values in ActionDispatcher args MUST be quoted strings

---

## Learned rules
This section is reserved for cross-cutting rules that don't fit cleanly
under one heading. Empty on first run.
