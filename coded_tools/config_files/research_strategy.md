# Research Lead

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary
You set research speed and topic to unlock higher tiers (blue→green→red). Research earns nothing directly but is the highest-leverage move in the game — it raises the capacity/excitement ceiling. Turn it on early and keep it on, without starving daily operating cash.
<!-- PLAYBOOK_SUMMARY:END -->

## What research does
Research earns $0 the day it runs, but a yellow-only park caps both capacity and park_rating — which caps guests and revenue. Unlocking higher tiers (rides/shops/staff) lifts capacity + rating → more guests → more revenue → funds the next unlock, so an earlier unlock compounds over more of the run while a late one caps the whole run. But an unlock only lands after research runs for several continuous, funded days — blue takes ~4 days at slow (~$8k total) — so it is worth switching on only once the park has banked enough cash to carry it through to the unlock; started underfunded, research stalls when cash dips and the tier stays locked.

## Research mechanics
Speed costs and IP value per day:
- slow: costs $2000/day, adds $1500/day to park value.
- medium: costs $8000/day, adds $3000/day to park value.
- fast: costs $32000/day, adds $6000/day to park value.
Further details are in research_economics.

Higher speed finishes a tier in fewer days (pushing the park ahead faster) but costs more per research point (fast ≈ 2× medium ≈ 4× slow), so the faster tiers only pay off while income covers their higher daily cost.

## Tips
- Don't propose research unless cash covers at least 3 days of `speed_cost` above daily recurring costs. If cash dips, research pauses on its own (progress is never lost) and the tier stays locked, so the spend so far buys nothing until cash recovers.
- Each subtype has four tiers (yellow < blue < green < red); you start at yellow, and research unlocks the rest in that order. `research_topics` is the list of subtypes to research (e.g. `["carousel"]`).
- `research_topics` is a QUEUE, and listing several costs no more than listing one — flat daily cost, same progress rate, one tier at a time. It only sets the order, breadth-first: the sim cycles one subclass per topic, so every listed topic reaches blue before any reaches green.
- That is a real trade-off. Listing ONE subtype rushes it to red fastest, but each later subtype then needs a fresh set_research — a whole step. Listing SEVERAL up front keeps unlocks diverse and avoids those extra steps, at the cost of slower depth on any single subtype.
- State handling:
  - only yellow unlocked: start slow research on rides.
  - new subclass just appeared in `available_entities`: research finished; immediately propose the next priority topic.
  - speed != none (in progress): don't reset unless cash fell below the safety threshold or strategy requires a pivot.
- Once started, research runs daily until you change the settings, funds run out, or all chosen topics unlock (progress pauses, never lost). It never auto-stops at your target tier — left on, it runs all the way to red.

## Learned rules (promoted from prior runs)