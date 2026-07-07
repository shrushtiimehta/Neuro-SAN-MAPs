## Episode Summaries
### ep=1
- RUN ABORTED as doomed: all 8 active trials rejected/falsified with note 'run aborted as doomed'; nothing promoted.
- CONFIRMED: none.
- FALSIFIED (abort override, not on merits): t1_1 coordinator (late-episode idling), t1_2/t1_6 research (turn research on/escalate tier), t1_3 shops (continuous shop-modify engine), t1_4 staff (janitor placement on valid path), t1_5/t1_7 rides (expand ride count / place roller_coaster tiers), t1_8 shops (protect rating with smaller restocks).
- CONTEXT NOTE for next run (do not re-propose as-is): final reward 34942 vs prior 49810 (down ~30%); telemetry shows steps 61-100 were 40 straight waits and step 100 collapsed (park_value 34698->500, num_rides 12->0, rating 29.86->20.0), so the abort/terminal wipe—not the trial rules—drove the low score. research_speed stayed 'none' all 100 steps.
- PRIORITY: diagnose the end-of-episode teardown / forced-wait behavior before re-testing build-cadence and research trials.

### ep=0
- RUN ABORTED as doomed (micro verdict 'doomed' x1 by step 80); per abort override, NOTHING promoted and ALL 10 active trials rejected/falsified.
- FALSIFIED (all, note 'run aborted as doomed'): t0_1 build-out pace (rides), t0_3 revenue mix / t0_6 restock tuning (shops), t0_4 handyman cleanliness (staff), t0_5/t0_7/t0_10 guest-draw & ride pricing (rides), t0_2/t0_8/t0_9 research timing (research).
- Not scored on merits: abort override governs, so none of these are 'proven wrong' by evidence — do NOT treat as evidence against re-proposing.
- Telemetry footnote for context: run actually reached step 100 (cum_end 49810, value collapsed to 500 at step 100 as park reset); reward_bands peaked at 962/step in 51-75 then fell to 268/step in 76-100 (22 waits). Research only ever reached 'slow' (never fast). These are observations, not confirmed rules.
- Priority next run: earlier/faster research (never got past slow), avoid the long wait-tail after step 80, and investigate the value/rating collapse at episode close.

- OUTCOME ep=1 trial_id=t1_1 domain=coordinator origin=macro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_2 domain=research origin=macro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_3 domain=shops origin=macro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_4 domain=staff origin=micro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_5 domain=rides origin=micro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_6 domain=research origin=micro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_7 domain=rides origin=micro outcome=falsified note='run aborted as doomed'
- OUTCOME ep=1 trial_id=t1_8 domain=shops origin=micro outcome=falsified note='run aborted as doomed'
