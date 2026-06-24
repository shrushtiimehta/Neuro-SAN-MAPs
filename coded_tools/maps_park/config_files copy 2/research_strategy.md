# research_lead - policy

## Research mechanics
Every ride, shop, and staff subtype has four subclasses: yellow < blue < green < red. The park starts with yellow only; research unlocks the rest in order blue → green → red per topic.

Action API: `set_research(research_speed, research_topics)` where `research_speed` ∈ {none, slow, medium, fast} and `research_topics` is a list of subtype names (e.g. `["carousel"]`). The simulator requires `research_topics` even when speed=none. Research continues daily until settings change, funds run out, or all chosen topics complete; if funds run out or all topics complete, speed automatically reverts to none and progress is paused (not lost).

Speed costs and IP value per day:
- slow: costs $2000/day, adds $1500/day to park value.
- medium: costs $8000/day, adds $3000/day to park value.
- fast: costs $32000/day, adds $6000/day to park value.

Higher speed finishes a tier in fewer days but costs more per research point (fast ≈ 2× medium ≈ 4× slow). Pick higher speed only when unlocking earlier earns back the extra cost over remaining days.

## Why research matters (the goal)
Research earns NOTHING directly (IP per day never covers its cost), yet it is the highest-leverage action in the game: it breaks the all-yellow ceiling. A yellow-only fleet caps BOTH capacity and park_rating. Reward COMPOUNDS - capacity and rating drive the per-turn `modify` payoff, which grows from ~100/turn early to 10k+/turn late - and higher tiers raise both inputs. GOAL: unlock blue->green->red as EARLY as affordable so the high-reward late-game engine runs for more of the episode. Front-load research; never defer it for "more revenue first." But keep it BALANCED - never sink so much into research that cash can't cover daily operating costs and keep building; running out of money stalls the whole park.

- Research one topic at a time (sequential is faster). Don't reset an in-progress topic unless pivoting.
- Don't propose research unless cash covers at least 3 days of `speed_cost` above daily recurring costs.
- Don't compute days/cost yourself — FinanceGate fills in `research_days` and checks affordability. Pick speed + target_tier wisely against remaining steps.
- Stop (speed=none) once the target subclass unlocks or cash drops below one day's research cost. Always pass `research_topics` even when speed=none.
- State handling:
  - only yellow unlocked: start slow research on rides.
  - new subclass just appeared: research finished; immediately propose the next priority topic.
  - speed != none (in progress): don't reset unless cash fell below the safety threshold or strategy requires a pivot.

## Learned rules
