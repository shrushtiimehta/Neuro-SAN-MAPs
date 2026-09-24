# Research Lead

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.
<!-- PLAYBOOK_SUMMARY:END -->

Research is the **HIGHEST-LEVERAGE** action in the game.
- Each ride, shop, and staff subtype has four subclasses, ordered by price: yellow (cheapest), blue, green, and red (most expensive). More expensive subclasses provide far greater benefits. Tiers unlock strictly in sequence per subtype (yellow (already available) → blue → green → red) — red cannot be bought directly.
- Research mainly drains cash — the returns come from **BUILDING** what it unlocks, so aim it at tiers you can reach and actually build in the park. Analyze all_economics in depth once research becomes affordable. Evaluate which rides, shops, and staffs are profitable and will be affordable based on current park status. Start small, build up to more expensive tiers. After your analysis, recommend set/one of research topics to prioritize.
- Start **INVESTING** in research as EARLY as you can afford. The sooner the tiers unlock, the sooner you can start earning A LOT MORE REVENUE. Play the long game. Never defer it for "more upfront revenue." But keep it BALANCED.

## Key attributes in research_economics:
- **research_speed** — `none` / `slow` / `medium` / `fast`. Faster research costs more money but unlocks tiers fast. Research continues daily until you change your settings or simulation forces research to stop because of funds running out, or all available subclasses for the chosen topics are unlocked.
  - Read `research_speed` every turn. If it says `none` and you didn't want that, re-issue `set_research`.
- **speed_progress** — research POINTS bought per day.
- **points_required** — points to lift ONE subtype ONE tier. 
- **days_** in `research_economics` carries number of days to unlock next tier. Plan speed well!
- **research_topics** — the SET of subtypes to research one by one.
  - Order of research is always fixed: `carousel` → `ferris_wheel` → `roller_coaster` → `drink` → `food` → `specialty` → `janitor` → `mechanic` → `specialist`. Runs breadth-first: one tier per topic, so every listed topic reaches blue before any moves to green. To **prioritize anything to red, list only one subtype.**

## Park current status (not set by you)
- **available_entities** — the unlock ledger: which subtypes have reached which tier. Growing this list is the goal.
- **research_operating_cost** — the current speed's daily cost.
- **daily_profit** — recurring daily P&L after research cost, excluding one-time ride/shop construction. Use this to judge whether operations can sustain research.
- **asset_investment** — successful ride/shop construction charged on this day and excluded from `daily_profit`.
- **next_unlock** — the live ETA, e.g. `{"subtype": "carousel", "tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Absent = research is off. Use to plan ahead.

## Learned rules (promoted from prior runs)
Increase research speed only when cashflow can stay positive and still fund at least one major build in each ten-turn window. (learned ep0)
