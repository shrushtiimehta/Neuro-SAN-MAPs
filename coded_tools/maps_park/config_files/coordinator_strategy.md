## Field ownership
- rides_manager / shops_manager / staff_manager return subtype/subclass/price but NO coordinates of placement.
- park_layout_planner manages ALL the (x,y) placement selection; NEVER guess coordinates.

## Decision-making based on:
- Each episode has 100 steps and we would like to reach at least $1,000,000 in cumulative rewards by the end of the 100 steps. Make sure you efficiently use each and every step properly to reach your goal.
- Always think in terms of long-term park value, not short-term cash. Prioritize investments that compound. Example: A ride that costs $10,000 today but earns $2,000/day pays back in 5 days and compounds for the rest of the episode — that is always better than hoarding cash. When choosing between two approved actions, prefer the one with the larger long-term return, even if it costs more upfront — provided you have cash / FinanceGate approved it and the episode has sufficient runway to recoup the cost.
- Research is a long-term investment: unlocking blue/green/red tiers enables higher-capacity and higher-excitement rides that dramatically increase park value. Start research as early as financially viable, not as a last resort.
- Every action must have a clear payoff rationale: what does this build/hire/research earn, and when does it break even? Also if in the last turn a certain set of rides/shops are resulting in profit try to build those again(research is still top priority).
- Avoid purely defensive actions (waiting, minor price tweaks) unless all productive investments are genuinely exhausted. Idle steps are permanently lost value.

## Safety rules (always)
- ActionDispatcher fires exactly once per step.
- Always pass research_topics field for set_research even when speed=none
- All numeric values in ActionDispatcher args MUST be quoted strings

## Learned rules

## Learned rules (promoted from prior runs)
When num_shops exceeds num_rides by more than 3, prioritize placing a new ride over adding another shop of an already-present subtype, to prevent diminishing returns from shop saturation and compound ride-driven rating growth. (learned ep0)
