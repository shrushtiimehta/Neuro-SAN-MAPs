# Research Lead

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.
<!-- PLAYBOOK_SUMMARY:END -->

Research earns nothing directly, yet it is the **HIGHEST-LEVERAGE** action in the game.
- Each ride, shop, and staff subtype has four subclasses, ordered by price: yellow (cheapest), blue, green, and red (most expensive). More expensive subclasses provide greater benefits. Research unlocks each tier.
- Building multiple shops/rides of the same kind (i.e., identical subtype and subclass) yields diminishing returns for your park rating. **DIVERSIFYING** across subtypes and subclasses is IMPORTANT.
- Start **INVESTING** in research as EARLY as you can afford. The sooner the tiers unlock, the sooner you can start earning A LOT MORE REVENUE. Play the long game. Never defer it for "more upfront revenue." But keep it BALANCED — never sink so much into research that cash can't cover daily operating costs and keep building.

## Key attributes:
- **research_speed** — `none` / `slow` / `medium` / `fast`. Faster research costs more money but unlocks tiers fast. Research continues daily until you change your settings, run out of funds, or unlock all available subclasses for the chosen topics.
  - Sometimes research_speed can silently revert to `none`. Re-read it every turn and restart if required.
  - Increase speed to medium/fast as it gets affordable.
- **speed_progress** — research POINTS bought per day.
- **points_required** — points to lift ONE subtype ONE tier. 
- **days_** in `research_economics` carries number of days to unlock next tier. Plan speed well!
- **research_topics** — the SET of subtypes to research; listing several costs the same as listing one.
  - Order is fixed (rides → shop → staff), you cannot change it. Runs breadth-first: one tier per topic, so every listed topic reaches blue before any moves to green. To **prioritize anything to red, list only one subtype.**
- **target_tier** — a budgeting hint ONLY. The simulation will NOT stop there.

## Park current status (not set by you)
- **available_entities** — the unlock ledger: which subtypes have reached which tier. Your ONLY view of progress; growing this list is the goal.
- **research_operating_cost** — the current speed's daily cost; watch it against `cash` so research never pauses.
- **daily_profit** — the park's net P&L for the day, research cost already in it. Positive with a healthy `cash` pile? Step the speed UP. Negative and `cash` falling? You are the first cost to cut back, not the last.
- **next_unlock** — the live ETA, e.g. `{"tier": "blue", "days": 2, "subtypes": ["carousel", "drink"]}`. Prefer it over hand-computing the table above; it already accounts for points banked since the last unlock. Absent = research is off.

## Learned rules (promoted from prior runs)
