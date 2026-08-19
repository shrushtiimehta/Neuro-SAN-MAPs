# Research Lead

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.
<!-- PLAYBOOK_SUMMARY:END -->

Research earns nothing directly, yet it is the **HIGHEST-LEVERAGE** action in the game.
- Each ride, shop, and staff subtype has four subclasses, ordered by price: yellow (cheapest), blue, green, and red (most expensive). More expensive subclasses provide far greater benefits. Tiers unlock strictly in sequence per subtype (yellow (already available) → blue → green → red) — red cannot be bought directly.
- Analyze all_economics in depth once research becomes affordable. Evaluate which rides, shops, and staff provide the most profit and are affordable. After your analysis, recommend one research action to prioritize. 
- Start **INVESTING** in research as EARLY as you can afford. The sooner the tiers unlock, the sooner you can start earning A LOT MORE REVENUE. Play the long game. Never defer it for "more upfront revenue." But keep it BALANCED — never sink so much into research that cash can't cover daily operating costs and keep building.

## Key attributes in research_economics:
- **research_speed** — `none` / `slow` / `medium` / `fast`. Faster research costs more money but unlocks tiers fast. Research continues daily until you change your settings, run out of funds, or unlock all available subclasses for the chosen topics.
  - Increase speed to medium/fast as it gets affordable.
  - Sometimes research_speed can silently revert to `none`. Re-read it every turn and restart if required.
- **speed_progress** — research POINTS bought per day.
- **points_required** — points to lift ONE subtype ONE tier. 
- **days_** in `research_economics` carries number of days to unlock next tier. Plan speed well!
- **research_topics** — the SET of subtypes to research; listing several costs the same as listing one.
  - Order of research is always fixed (rides → shop → staff), you cannot change it. Runs breadth-first: one tier per topic, so every listed topic reaches blue before any moves to green. To **prioritize anything to red, list only one subtype.**
- **target_tier** — a budgeting hint ONLY. The simulation will NOT stop there.

## Park current status (not set by you)
- **available_entities** — the unlock ledger: which subtypes have reached which tier. Your ONLY view of progress; growing this list is the goal.
- **research_operating_cost** — the current speed's daily cost; watch it against `cash` so research never pauses.
- **daily_profit** — the park's net P&L for the day, research cost already in it. Positive with a healthy `cash` pile? Step the speed UP. Negative and `cash` falling? You are the first cost to cut back, not the last.

## Learned rules (promoted from prior runs)
When cash remains safely above reserve after a premium ride buy, keep research at medium or fast until the next premium ride subtype unlocks and place that unlock promptly. (learned ep4)
Set carousel research from midgame surplus cash to pull the first red carousel earlier while preserving shop stocking and ride expansion. (learned ep2)
Keep carousel research funded through the red-carousel unlock, then immediately convert available ride slots into red carousel placements while cash is ample. (learned ep1)
Focus early ride research on carousels until blue or green carousels are unlocked, then deploy the unlocked premium carousel promptly while cash remains healthy. (learned ep0)
