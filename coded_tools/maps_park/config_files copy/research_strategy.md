# research_lead - policy

- **One topic per call:** research sequentially (parallel topics are slower). Don't reset an in-progress topic unless pivoting.
- **Cash floor:** do not propose research unless current cash covers at least 3 days of the proposed `speed_cost` without dipping below daily recurring costs.
- **Priority order (rides unlock capacity and revenue fastest):**
  1. carousel or ferris_wheel - unlock blue tier first for capacity gains
  2. roller_coaster - only after blue rides are placed and profitable
  3. drink/food shops - once ride revenue is stable
  4. staff - lowest priority; yellow staff covers early game
- **Speed tradeoff:** do NOT compute days/cost yourself - FinanceGate enriches every set_research proposal with `research_days` (= ceil(points_required / speed_progress)) and checks affordability against current cash + daily_operating_cost. Your job is to PICK speed + target_tier wisely against remaining horizon. IP earned per day never covers research cost - research is a capital investment in unlocking tiers, not a revenue source.
- **Stopping:** stop research (speed=none) once the target subclass is unlocked or cash drops below one day's research cost. When stopping, still pass the current topic in `research_topics` (e.g. `["carousel"]`) - the simulator requires the field even when speed is none.
- **State handling** (read `status.research_speed` and `status.available_entities`):
  - speed='none' AND only yellow unlocked everywhere (initial): research has never started - the single highest-leverage move, since yellow-only caps BOTH capacity and rating (see rides playbook for the intensity penalty). As soon as cash ≥ 8000 AND ≥ 1 ride is profitable, START slow research on carousel or ferris_wheel, target_tier=blue. Do NOT keep deferring for "more revenue first" - that is exactly why prior episodes never unlocked a tier and plateaued.
  - speed='none' AND a new subclass appeared vs. prior turn (completed): research just finished. Immediately propose the next topic in priority order.
  - speed != 'none' (in progress): do not reset unless cash dropped below the safety threshold or strategy requires a pivot.

## Learned rules
