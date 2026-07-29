# Research Lead

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.
<!-- PLAYBOOK_SUMMARY:END -->

## What research does
Research earns nothing directly, yet it is the **HIGHEST-LEVERAGE** action in the game.

GOAL: The park has four tiers — yellow → blue → green → red — and reward COMPOUNDS as you climb them. Research is what unlocks each tier; only then can you build the higher-tier assets that raise the capacity and revenue of your rides/shops/staff and earn high rewards. A yellow-only fleet caps BOTH capacity and park_rating, so start researching as EARLY as you can afford — the sooner tiers unlock, the more of the episode the high-reward late-game engine runs. Never defer it for "more revenue first." But keep it BALANCED — never sink so much into research that cash can't cover daily operating costs and keep building.

## Levers you SET (via `set_research`):
- **research_speed** — `none` / `slow` / `medium` / `fast`; `none` = no progress. Higher speed unlocks a tier in fewer days but costs more per day.
- **research_topics** — the QUEUE of subtypes to research, in order.

## Research status readouts (reported per ride, not set by you)
- **available_entities** — the unlock ledger: which subtypes have reached which tier. Your ONLY view of progress; growing this list is the goal.
- **research_operating_cost** — the current speed's daily cost; watch it against `cash` so research never pauses.

## Tips
- Propose research only if cash covers at least 3 days of `speed_cost` above daily recurring costs otherwise return []. Do NOT let the cash dip below research_operating_cost, as it results in research pausing (progress is never lost) and the tier stays locked, so the spend so far buys nothing until cash recovers.
- Each subtype has four tiers (yellow < blue < green < red); you start at yellow, and research unlocks the rest in that order. `research_topics` is the list of subtypes of rides/shop/staff to research (e.g. `["carousel"]`).
- `research_topics` is a QUEUE, and listing several costs no more than listing one. Make sure you use it to set the order to run research breadth-first: it researches one tier per topic, so every listed topic reaches blue then research moves to green and so on. Listing a few up front keeps unlocks diverse and avoids those extra steps to change the research topic, at the cost of slower depth on any single subtype.
- Once started, research runs daily until you change the settings, funds run out, or all chosen topics unlock (progress pauses, never lost). It never auto-stops at your target tier — left on, it runs all listed subtypes to red.
- Higher speed finishes a tier in fewer days (pushing the park ahead faster) but costs more per research point (fast ≈ 2× medium ≈ 4× slow). Start increasing the speed once the park's income is able to bear the higher daily cost.

## Learned rules (promoted from prior runs)