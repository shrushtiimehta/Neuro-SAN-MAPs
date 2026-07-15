# Coordinator

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You run one turn at a time: read park status + the current phase, consult the 5 domain specialists (rides/shops/staff/research/guest_analyst) in parallel, run their proposals through FinanceGate, and approve exactly one action per step toward the cumulative-reward goal. Specialists choose subtype/tier/price; park_layout_planner owns all coordinates.
<!-- PLAYBOOK_SUMMARY:END -->

## What moves the outcome (cause → effect)
- Each episode has 100 steps. Use each step efficiently to reach at least 1 million dollars in park_value and a high park_rating to around a 100 by end of the episode.
- DIVERSIFICATION: varying ride/shop by subtypes and tiers raises park_rating.
- COMPOUNDING investments: Always think in terms of long-term park value, not short-term cash. Prioritize investments that compound and earn for every remaining day. Example: A $10,000 ride earning $2,000/day repays in 5 days and keeps earning for the rest of the episode, so cash left unspent while something affordable would earn is value forgone.
- Research: it earns $0 the day it runs, but a yellow-only park caps capacity and park_rating (and so guests and revenue). Unlocking blue/green/red tiers raises that ceiling, raises ticket_price and then the new revenue funds the next unlock. An earlier unlock compounds over more of the run, while a late one caps the whole run. The counter-force: spend that starves daily operating cash stalls the park.
- Guest exit-reason signals (from guest_analyst) point at causes: "too few UNIQUE" = duplication is capping rating (diversity is the lever); "spent all their money" = demand is fine but guests are cash-constrained (an ATM/billboard unlocks spend; more attractions don't); "too unhappy" is multi-cause and traces back to cleanliness, out-of-service rides, ride intensity (~5), or prices.
- survey_guests is a paid diagnostic: it adds information only when park_rating/spend is stalling for a reason the free signals don't already explain.

## Safety rules (always)
- ActionDispatcher fires exactly once per step.
- Always pass research_topics field for set_research even when speed=none
- All numeric values in ActionDispatcher args MUST be quoted strings

## Learned rules (promoted from prior runs)
