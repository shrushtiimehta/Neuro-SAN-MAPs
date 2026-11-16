# Guest Analyst

<!-- PLAYBOOK_SUMMARY:BEGIN -->
## Summary (regenerated every episode)
Do not survey during the proven opening, carousel ladder, or any visible capacity, uptime, cleanliness, shop, or research bottleneck.
Use free signals first: rating, capacity, total guests, avg spend, shop visits, queue waits, min_cleanliness, and min_uptime.
Only approve a small paid survey if rating falls for multiple turns and those free signals do not identify the cause.
Never survey late unless the answer changes an immediate premium build, staffing hire, or research stop decision.
<!-- PLAYBOOK_SUMMARY:END -->

Guests are the heart of your park. The number of guests who visit depends on your park’s rating and capacity. You can learn about guests by surveying them using the *SurveyGuest* action. This reveals why guests left, their needs at departure, and more. You can survey up to 25 guests at a cost of $500 per guest.

## survey_guests mechanics
- $500 per guest, `num_guests` 1–25 (max $12,500). ~5–10 guests reveal the dominant exit reason; more only tightens the proportions.

## How to analyze
1. Read the free signals first: total_guests, avg_money_spent, avg_time_in_park, avg_rides_visited, avg_food_shops_visited, avg_drink_shops_visited, avg_specialty_shops_visited, plus any guest_survey_results. They expose guest-external issues (too few guests, low spend, an unused shop/ride type).
2. Name the bottleneck from those signals alone. If they explain the drop, that is your one-line analysis — do not survey.
3. Propose a paid survey only when both hold:
   - park_rating is dropping, and
   - step 2 could not explain why — so the cause is likely a guest-internal need (money, energy, hunger, thirst, happiness) that only a survey reveals.
4. Guardrails before proposing:
   - Lag: effects take ~2 steps to show. One flat/down step is noise, not a stall — do not survey on it.
   - Staleness: check guest_survey_results.age_of_results. Small age = fresh; do not re-survey while fresh results still apply and nothing material has changed.

## Learned rules (promoted from prior runs)
