## Episode Summaries
### ep=1
## Episode 1 Outcome Summary (reward: 19,495 → 72,184, Δ+52,689 / +270%)

- **CONFIRMED — t0_1 (research domain):** Rule "activate research at 'slow' speed early and sustain it until a non-yellow-tier asset unlocks" is validated. Research set to 'slow' at step 44; blue-tier carousel placed step 70. Promoted to playbook_research. Do NOT re-propose this rule.

- **FALSIFIED — t1_1 (staff domain):** Staff-placement validation trial failed: four consecutive "Invalid location for staff. Must be on a path or in an attraction" rejections at steps 5, 15, 20, 31. The agent repeatedly attempted invalid staff placements; the rule was not internalized. Re-trial logged as t1_1 for episode 2 with tighter mechanic-churn framing.

- **FALSIFIED — t1_2 (shops domain):** Shop-upgrade priority rule failed: shops frozen at 7 from step ~19 onward; cash ranged 8k–49k in steps 80–99 yet no new shop was placed. shop_revenue plateaued at ~1,400–1,629 while expansion was clearly affordable. Do NOT re-propose without a concrete cash-threshold trigger.

- **FALSIFIED — t1_3 (coordinator domain):** Mechanic-churn prevention rule failed: four same-tier mechanic remove→place cycles at steps 83→84, 87→88, 90→91, 96→97 (8 wasted actions); failure criterion was ≤1 such pair. Re-trial logged as t1_1 (staff domain) for episode 2.

- **CRITICAL POSITIVE — late-game modify loop (steps 82–99):** Food/drink `modify` actions drove the highest per-step rewards (+2,826, +2,767, +2,651, +2,557, +2,315, +2,252). This loop only became powerful after roller_coasters (steps 35, 49, 52, 55, 71) and blue-tier carousels (steps 70, 74, 77, 79) raised park throughput. Future episodes should prioritize unlocking blue-tier assets early to extend this window.

- **CRITICAL NEGATIVE — mechanic churn and staff rejections wasted ~12 combined steps** in the 80–100 window, suppressing what could have been an additional 25,000+ reward. Avoid same-tier remove→re-place cycles entirely; never attempt staff placement off-path.

- **KEY PATTERN TO AVOID:** Shop stagnation. With ample cash (8k–49k) and only 7 shops, the agent missed multiple affordable expansions. A cash-threshold rule (e.g., place a new shop when cash > 5,000 and num_shops < 10) should be trialed in episode 2.

### ep=0
## Episode 0 Outcome Summary (reward=19495.0, prior=0, delta=+19495)

**CONFIRMED (do not re-propose):**
- **t2_1 [rides]:** Keeping num_rides ≥1 at all times is confirmed safe and profitable — min observed was 2 (s24/s26); park_rating never dropped below 14.63 after ride placements.
- **t0_1 [coordinator]:** Placing rides when shop-count > ride-count+3 yields positive reward within 5 steps (s29: +259, s34: +281, s37: +181, s40: +136). Rule is stable; do not re-propose.
- **t0_3 [layout]:** Avoiding tile retries after rejection kept placement failures to ≤2 in steps 61–100 (s73, s98). Confirmed rule in layout playbook; do not re-propose.

**FALSIFIED (do not re-propose):**
- **t1_2 [shops]:** Hypothesis that shops grow when cash>5000 was falsified — num_shops flat at 12 from s39–s93 (55 steps) with cash repeatedly exceeding 5000 (max 7232 at s80). Root cause likely elsewhere (capacity or logic constraint, not cash).
- **t0_2 [staff]:** Staff placement strategy generated identical rejections at s15 and s30 ("Invalid location — must be on path or attraction"). Same failure repeated; placement rule is wrong. Do not re-propose without path/attraction pre-check.
- **t0_4 [rides]:** Remove+place churn (3 pairs: ferris_wheel, mechanic, carousel) in s81–100 with zero `move` actions confirmed as wasteful. Churn incurs ~34% asset haircut; falsified as a viable late-episode tactic.

**NEW TRIAL LOGGED (episode 1):**
- **t0_1 [research]:** Test activating research at 'slow' speed immediately after first ride+shop pair is placed, and not reverting to 'none'. Episode 0 made two research toggles (s57, s81) both immediately reversed (s83 reset), netting −248 reward and zero tier unlocks — entire episode ran on yellow-only assets despite cash headroom from s29+.

**CRITICAL STEPS TO REPLICATE:**
- s29, s34, s37, s40: Ride placements under shop>ride+3 imbalance — all profitable, all stabilized rating. Pattern to preserve.

**KEY PATTERNS TO AVOID (episode 1):**
- Toggling research on then immediately off — costs reward, unlocks nothing.
- Repeating staff placement in invalid tiles without a path/attraction pre-check.
- Remove+place asset churn in late steps instead of using `move`.

### ep=1
- CONFIRMED (staff, t1_1): When min_uptime craters below 0.8 with roller_coasters present, placing a mechanic restores uptime and yields reward (s34 uptime 0.28, s35 0.0 → mechanic placed s36 → uptime 0.96/1.0 with +400 then +1028). Promoted to playbook; do not re-propose.
- CONFIRMED (rides, t1_3): Favor high-tier ride placements over carousels late-game; high-tier placements drove the largest rewards (rc s73 +1910, s51 +1311; ferris s57 +1203, s59 +1023), carousel removals were net positive (s71 +359), and park_rating held ≥24 until terminal reset. Promoted to playbook; do not re-propose.
- NOT_APPLIED / still active (research, t1_2): Upgrade-research-above-slow rule never fired — runner used only 'slow' speed all episode and never selected 'fast' even with cash >3000 (s32 3358, s34 4847). Cannot confirm/falsify; carried forward unchanged. Do not re-propose a duplicate; the existing active trial covers it.
- FALSIFIED: none this episode.
- REWARD DROP CONTEXT: Final reward fell sharply 352604.0 → 47245.0, but this is a step-100 teardown/reset artifact (num_rides→0, num_shops→0, park_value→500, rating→20.0), NOT a mid-episode strategy failure. Cumulative reward grew monotonically through s99 (46530@s99 → 47245@s100). Do not propose trials chasing the terminal reset — it is a sim end-of-episode artifact with no falsifiable behaviour change.
- NEW TRIAL for next episode (shops, t1_2): Probes the untested shops domain — num_shops frozen at 7 from s19–s99 while cash idled 8k–13k and shop_revenue plateaued (~1378@s55, ~1420@s99). Tests adding/upgrading shops when cash>5000 and shop count is stale.
- PATTERN TO AVOID: Do not re-propose layout/zero-rejection-criterion trials (prior t0_3 falsified on an unachievable zero-rejection metric) despite continued placement-collision signal.

### ep=0
Episode 0 close-out (final cum_reward=352604.0, prior=0):

- CONFIRMED (rides, t0_1 — promoted to playbook_rides): Adding varied rides breaks the single-ride park_rating cap. num_rides ≥2 from step11 (10 rides @step21); park_rating exceeded 12.0 repeatedly (24.74@step22, 36.83@step34, 34.59@step44); cum_reward@step45=32950.0 ≫ step20's 87.0. Do not re-propose.
- CONFIRMED (research, t0_2 — promoted to playbook_research): set_research→slow when cash is healthy unlocks a non-yellow subclass. Applied @step32 (cash=5055); carousel/blue placed @step40; cum_reward@step55=55219.0 ≫ step20's 3573.0; no sub-one-day drawdown. Do not re-propose.
- FALSIFIED (layout, t0_3 — not promoted): The 'zero additional path-collision place rejections' criterion was tripped by three 'Tile already contains a path' rejections at step49 (9,8), step50 (11,9), step67 (11,8). Agent kept retrying occupied/path tiles. Do NOT re-propose this rule unchanged; any layout trial needs a different, achievable criterion that tolerates/explains retry behavior.
- INCONCLUSIVE: none this episode.
- Patterns to avoid next episode: (1) don't re-propose rides-variety or research-slow rules (already in playbooks); (2) avoid layout criteria demanding zero path-collision rejections given observed retry-on-occupied behavior; (3) watch min_uptime on roller_coasters — new trial t1_1 (staff) tests proactive mechanic hiring at min_uptime<0.8 (cites steps 23/61/77/78/89/97/99).

- OUTCOME ep=1 trial_id=t1_1 domain=staff outcome=confirmed note='min_uptime cratered <0.8 at s34 (0.28) and s35 (0.0) with roller_coasters present; mechanic placed at s36 restored uptime 0.0->0.96 (s37=1.0) and gave +400 then +1028. Single in-window applicable case succeeded (100% >= 70% threshold).'
- OUTCOME ep=1 trial_id=t1_2 domain=research outcome=not_applied note='Upgrade-above-slow never occurred: research_speeds_used=['slow'] only. 'fast' tier never selected even though cash exceeded 3000. No applied entry matches the trial action; cannot be evaluated.'
- OUTCOME ep=1 trial_id=t1_3 domain=rides outcome=confirmed note='Steps 61-100 no carousels placed; high-tier placements drove largest reward (rc s73 +1910, s51 +1311; ferris s57 +1203, s59 +1023); carousel removals net positive (s71 +359). park_rating held >=24 until terminal reset. Success criterion met.'
- OUTCOME ep=1 trial_id=t0_1 domain=research outcome=confirmed note='Research set to slow at step 44; a blue-tier carousel placed at step 70 — first non-yellow asset unlocked. Failure criterion not tripped (research_speeds_used = ['slow', 'None']).'
- OUTCOME ep=1 trial_id=t1_1 domain=staff outcome=falsified note='Step 31 rejection: 'Invalid location for staff. Must be on a path or in an attraction.' — occurs within the trial window (step 21+), directly trips the failure criterion.'
- OUTCOME ep=1 trial_id=t1_2 domain=shops outcome=falsified note='All shops remained yellow-tier through step 80; cash at step 80 was 8,512 (far above 500 headroom threshold) — no non-yellow shop placed before step 80.'
- OUTCOME ep=1 trial_id=t1_3 domain=coordinator outcome=falsified note='Three mechanic remove→place-same-tier churn cycles within steps 80–100 (steps 83→84, 87→88, 90→91); failure criterion requires ≤1.'
