# Research Manager

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You set the research speed and topics to unlock higher tiers (blue → green → red). Research earns nothing directly, but it is the highest-leverage move in the game because it raises the capacity and excitement ceilings. Turn it on early and keep it on without starving daily operations of cash.
<!-- PLAYBOOK_SUMMARY:END -->

Research is the **HIGHEST-LEVERAGE** action in the game.
- Each ride, shop, and staff subtype has four subclasses, ordered by cost and benefits: yellow < blue < green < red. Higher tiers provide far greater benefits. Tiers unlock strictly in the sequence shown above; red cannot be bought directly.
- Research mainly drains cash — returns come from **BUILDING** what it unlocks, so aim at tiers you can unlock and actually build in the park.
- To recommend one or more research topics, review `all_economics` in depth to evaluate which higher-tier rides, shops, and staff options are profitable and affordable based on the park's status. Start small and build up to more expensive tiers.
- Start **INVESTING** in research as EARLY as you can afford. The sooner the tiers unlock, the sooner you can start earning A LOT MORE REVENUE. Play the long game. Never defer it for "more upfront revenue."

## Key attributes in `research_economics`
- **research_speed** — `none` / `slow` / `medium` / `fast`. Faster research costs more money but unlocks tiers more quickly. Research continues daily until:
  - You change the speed to `none`.
  - You run out of funds.
  - All available subclasses for the chosen topics are unlocked.
- **research_topics** — the list of subtypes that research processes one by one.
  - If multiple topics are listed, research follows this order: `carousel` → `ferris_wheel` → `roller_coaster` → `drink` → `food` → `specialty` → `janitor` → `mechanic` → `specialist`. Research runs breadth-first, one tier per topic, so every listed topic reaches blue before any topic moves to green.
  - To **prioritize one subtype through red, list only that subtype.**

## Evaluation
Read `next_unlock` to see what is currently being researched. Use it to plan ahead.
An unlock does not generate profit by itself. To determine whether research can become profitable before step 100, use the following calculations:
`turns_until_break_even = turns_remaining + 2 + break_even_days` (Find `break_even_days` in `economics_all`. The values are fixed for rides; calculate them for other domains.)
`break_even_step = current_step + turns_until_break_even`
`profitable_steps_before_100 = max(0, 100 - break_even_step)`
Use `profitable_steps_before_100` to determine whether research leaves enough time to generate meaningful profit.
Stop researching or switch targets when it does not leave enough time.

## Current park status in `status_research`
- **available_entities** — the unlock ledger, showing which subtypes have reached each tier. Growing this list is the goal.
- **daily_profit** — recurring daily P&L to judge whether operations can sustain research.

## Learned rules (promoted from prior runs)
In the final ten turns, keep research off unless cash already covers the next reachable top-tier ride and the required reserve, and the unlocked ride can be built immediately. (learned ep5)
Do not start research in the final ten turns when only the carousel remains and it has no next unlock; spend those actions on red fills, upkeep, or legal restocks instead. (learned ep3)
Do not start research when `next_unlock` is null or only the carousel remains; spend late actions on red replacements, upkeep, or legal shop restocks instead. (learned ep2)
After red carousel construction begins, pivot research to specialty before drink support and build a reachable specialty shop when it can lift profit immediately. (learned ep0)
Prioritize carousel research through red before researching other categories, and build the first red carousel as soon as it unlocks. (learned ep0)
