# research_lead - policy

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary (regenerated every episode)
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.
<!-- PLAYBOOK_SUMMARY:END -->

## Research mechanics
Every ride, shop, and staff subtype has four subclasses: yellow < blue < green < red. The park starts with yellow only; research unlocks the rest in order blue → green → red per topic.

Action API: `set_research(research_speed, research_topics)` where `research_speed` ∈ {none, slow, medium, fast} and `research_topics` is a list of subtype names (e.g. `["carousel"]`). The simulator requires `research_topics` even when speed=none. Research continues daily until settings change, funds run out, or all chosen topics complete; if funds run out or all topics complete, speed automatically reverts to none and progress is paused (not lost).

Speed costs and IP value per day:
- slow: costs $2000/day, adds $1500/day to park value.
- medium: costs $8000/day, adds $3000/day to park value.
- fast: costs $32000/day, adds $6000/day to park value.

Higher speed finishes a tier in fewer days but costs more per research point (fast ≈ 2× medium ≈ 4× slow). Pick higher speed only when unlocking earlier earns back the extra cost over remaining days.

## Why research matters (the goal)
Research earns NOTHING directly (IP per day never covers its cost), yet it is the HIGHEST-LEVERAGE action in the game. A yellow-only fleet caps BOTH capacity and park_rating. Reward COMPOUNDS when due to research and higher tier building increases the capacity and rating of the rides/shop/staff. GOAL: unlock blue->green->red as EARLY as affordable so the high-reward late-game engine runs for more of the episode. Never defer it for "more revenue first." But keep it BALANCED - never sink so much into research that cash can't cover daily operating costs and keep building; running out of money stalls the whole park.

- Research one topic at a time (sequential is faster). Don't reset an in-progress topic unless pivoting.
- Don't propose research unless cash covers at least 3 days of `speed_cost` above daily recurring costs.
- Don't compute days/cost yourself — FinanceGate fills in `research_days` and checks affordability. Pick speed + target_tier wisely against remaining steps.
- Stop (speed=none) once the target subclass unlocks or cash drops below one day's research cost. Always pass `research_topics` even when speed=none.
- State handling:
  - only yellow unlocked: start slow research on rides.
  - new subclass just appeared: research finished; immediately propose the next priority topic.
  - speed != none (in progress): don't reset unless cash fell below the safety threshold or strategy requires a pivot.

## How you move park_rating (status carries `park_rating`)
Research unlocks higher tiers (blue→green→red), and higher-tier rides carry more excitement and capacity — more excitement raises rating and more capacity lets more guests visit. Staying all-yellow caps both, so unlock higher tiers early.

## Learned rules

## Learned rules (promoted from prior runs)
Turn research on (at least slow) as soon as a ride and a shop both exist and sustain it without interruption until a higher (non-yellow) tier is confirmed unlocked. (learned ep0)
Activate research at 'slow' speed as soon as a ride and at least one shop are placed, and sustain it without reverting to 'none' until a non-yellow-tier asset is confirmed unlocked — early, uninterrupted research compounds across the episode by enabling higher-tier rides and shops that outperform any individual yellow-tier placement. (learned ep1)
As soon as cash covers ≥3 days of slow research cost, set slow research to break the all-yellow ceiling.
