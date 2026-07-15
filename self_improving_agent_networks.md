# Self-Improving Agent Networks: Getting Better at a Task Without Changing a Single Weight

## The idea

LLMs are non-deterministic. Run one a hundred times and the hundredth attempt might look like the first or maybe even worse — same weights, same prompt, same or worse mistakes on repeat — because all of its competence is frozen in the model, and nothing about the ninety-nine attempts before it ever sticks. Making the model bigger raises the starting point; it does not give the agent a way to learn from its own runs.

A **self-improving agent network** is our term for the alternative: a multi-agent system that gets measurably better at a task across repeated attempts **with no weight updates and no human editing its prompts between runs** but only persistent memory, middleware and tool calling. The only thing that changes from one attempt to the next is a memory the system writes, curates, and is forced to justify — for itself.

The approach rests on a few principles, each of which we make concrete later:

- **Separate acting from reflecting.** One fast network acts. Slower networks do nothing but read what happened and decide what the acting network should try next. They never share a conversation — only plain-text notes on disk.
- **Earn every memory.** No lesson is kept because a run went well. Each proposed lesson is written as a falsifiable hypothesis — a rule, a success condition, a failure condition — run live, and then judged against an objective log. Confirmed lessons are kept; falsified ones are deleted and recorded so they cannot come back.
- **Models decide, code enforces.** The models supply judgment. All arithmetic, bookkeeping, and file edits are performed by deterministic code, so the acting network can never quietly grade its own homework.
- **Never lose ground.** Proven lessons accrete into a permanent store that survives a cold restart, and every new attempt plans from the best run ever recorded — never the most recent one — so a bad attempt cannot drag the next one down.
- "Underirable states:"

None of these pieces are individually new. Actor–critic separation is decades old in reinforcement learning, and writing lessons down in natural language has real precedent. What makes a network *self-improving* rather than merely *self-modifying* is the discipline connecting them: a memory that has to prove itself before it is trusted.

## Why this needs a hard testbed

A self-improving system is only as trustworthy as the ground truth it grades itself against. If the objective can be gamed, or the record of what happened can be spun by the same model that produced it, the system will "improve" straight into a delusion — learning wrong lessons with total confidence. To test the idea honestly we needed a task with two properties: a **single, objective score** the agent cannot narrate its way around, and enough **genuine difficulty** that improvement is unambiguous and there is real room to climb.

Mini Amusement Parks fits both.

## The testbed: Mini Amusement Parks (MAPs)

[Mini Amusement Parks (MAPs)](https://maps.skyfall.ai/) is a business-simulation benchmark for AI research, released by Skyfall AI ([arXiv:2511.15830](https://arxiv.org/abs/2511.15830)). The player is the manager of an amusement park and takes **exactly one action per day** over a fixed horizon; the park then opens, guests stream in and interact with it for a full day, and the day's results feed the next decision. The objective is to **maximize the park's total value** by the end of the horizon.

We run the **medium** difficulty: a 100-day horizon where only the cheapest ("yellow") tier of each attraction is available at the start, and better tiers must be unlocked through research. That single constraint is what makes medium hard — the strongest strategies are literally locked behind a decision to spend money and time now for a payoff much later.

The manager's daily action is chosen from a small but consequential set:

- **Build, move, remove, or re-price** rides and shops. Rides are the only thing that draws guests — a park with no rides gets no visitors — and each has a capacity, an excitement score, a breakdown rate, and per-operation costs. Shops (drink, food, specialty) cater to guest needs; run one dry and it goes out of service and drags the park's rating down.
- **Hire staff** — janitors to clean, mechanics to repair broken rides, specialists for support roles.
- **Set research** — pick a speed (none/slow/medium/fast, at \$0 / \$2k / \$8k / \$32k per day) and topics, to unlock higher-tier attractions in blue → green → red order.
- **Survey guests** — pay \$500 per guest surveyed to learn *why* guests are leaving, up to 25 at a time.
- **Wait** — run the day with no new action.

Guests are the engine underneath all of it. How many arrive depends on the park's **capacity** (set entirely by rides) and its **rating** (driven by ride excitement, cleanliness, balanced intensity, and guests leaving happy). Each guest arrives with limited money and energy, grows hungry and thirsty over the day, seeks out matching attractions, and leaves — or leaves *early* and unhappy — if its needs go unmet. Rides break down. Guests litter. Nothing about the reward is handed to the agent as a formula; it must be discovered by running the park and watching what happens.

### Why MAPs is a good benchmark

Most agent benchmarks isolate a single capability. MAPs' contribution is that it **unifies four interconnected challenges into one environment** ([paper](https://arxiv.org/abs/2511.15830)):

1. **Long-horizon optimization under stochasticity** — a hundred coupled decisions, where the best move often pays off dozens of days later, against a simulator full of random breakdowns and guest behavior.
2. **Sample-efficient active learning from sparse experience** — the dynamics are not given; the agent must learn them from a handful of noisy days.
3. **Spatial reasoning** — attractions must be placed on a grid, adjacent to paths, near the food and drink that high-traffic rides create demand for.
4. **World modeling** — anticipating the downstream consequences of an action before committing scarce cash to it.

It is also, bluntly, *unsolved*. Humans outperform state-of-the-art LLM agents by **6.5× on easy mode and 9.8× on medium**, and the strongest frontier models reach only about 10% of human performance. That headroom is what makes it useful: there is a great deal of room to improve, and improvement is unambiguous. And because the benchmark is **external** — we did not build it, cannot tune it to flatter ourselves, and cannot game it without genuinely running a better park — it provides exactly the hard-to-fake ground truth a self-improving system needs.

---

# Implementation

The principles above are general. Here is how we instantiated them for MAPs.

## Running the park: the agent network

We do not point a single monolithic prompt at the game. The park is run by an **agent network**: a front-man coordinator that, each day, reads the current state of the park and consults a set of **domain specialists** — one each for rides, shops, staff, research, layout, and guest surveys. Each specialist reasons only about its own area and carries its own plain-text **strategy playbook**. The coordinator weighs their input, selects exactly one action for the day, and commits it.

The specialists *advise*; they do not do arithmetic or touch the simulator. A proposed action is handed to deterministic code that checks whether the money works and then dispatches it to the game — the split we describe under [Guardrails](#guardrails-the-model-decides-the-code-enforces).

That is enough to *play* MAPs. It is not enough to *improve* at it. For that we add a second and third clock.

## Three clocks

The system is built from separate agent networks running on three different clocks. None shares a conversation; they communicate only through plain-text files on disk — the "separate acting from reflecting" principle, made concrete.

- **The player** — the network above. It runs fast, one action per day, and does not look back.
- **The watcher** — a slower network that wakes up *during* a run, every ten days, reads the profit trajectory so far, and asks a single question: is this run still worth finishing? It never touches the controls. It can only record ideas to try next, and call time of death on a run that is clearly lost.
- **The planner** — the slowest network, running *between* runs. Before each new attempt it compares the **best run ever recorded** against the most recent one, writes the plan the next attempt will follow — a day-phased checklist plus a short strategy brief the player re-reads every turn — retires ideas that stopped paying off, and proposes fresh ones to test.

The design bet is that the player can afford to be fast and a little reckless *because* something slower and more skeptical always gets the last word on what counts as real — and something slower still decides what the next run even attempts.

## Earning memory: the falsifiable trial protocol

This is where "earn every memory" becomes machinery. An LLM left to its own devices will happily conclude that a lucky run proved a theory. This system is not permitted to. Every idea it wants to keep must first be framed as a **falsifiable hypothesis**:

1. **A rule** — a general instruction, not a one-off observation.
2. **A success condition** — a specific metric, a direction, and a window to check it in.
3. **A failure condition** — the exact result that would prove it wrong.

These are not a mindset; they are files on disk. The rule lives in one file, its success-and-failure criteria in a second, and every verdict in a third — an append-only **outcome ledger**. That ledger is the memory of what has already been tried: a falsified idea leaves a permanent record behind, so it cannot quietly return as a "new" proposal three runs later.

The hypothesis then actually runs — live, steering real decisions for a full episode — and afterward is checked against the deterministic log, never against the model's own account of what happened:

- **Confirmed** → written permanently into the playbook.
- **Falsified** → removed, and logged so it is never proposed again.
- **Inconclusive** → carried forward, untouched, for another trial.

Nothing graduates to "known" without surviving a fair test it could have failed.

## Guardrails: the model decides, the code enforces

There is a quieter failure mode underneath all of this. If the *same* model both makes a decision and does the bookkeeping — totals the budget, estimates whether a ride will ever pay for itself, edits its own playbook — then it is grading its own homework. The numbers its judge later reads are numbers its actor could have fudged, and a self-graded memory is worth nothing.

So the models only ever supply **judgment**. Every mechanical step around them is deterministic code with no LLM inside:

- A **finance gate** does the arithmetic. One-time cost, daily burn rate, how many days a ride needs to break even, whether the park can even afford to run a research project to completion — all computed from the game's economics tables, not estimated by a model. The player *proposes* an action; the gate returns a flat approve or reject.
- A **pre-step validator** checks the proposed action against the rules *before the simulator advances at all*. If it is malformed, unaffordable, or against policy, the environment is left untouched and the player is re-prompted with the reason it was rejected. Only a valid action ever reaches the game.
- A **playbook editor** performs the actual file edits — add a learned rule, replace one, remove one — but only after the planner has decided what should change. It physically cannot delete the hand-written baseline: only rules the system taught itself are removable.

The point is not tidiness. It is that the log the judge reads is produced by code the actor cannot spin. "Judged against the log, never the model's own account" only means something if the log was never the model's to edit.

## Never losing ground: inheritance and the champion episode

Improvement does not come from the trials themselves — proposing plausible ideas is the easy part. It comes from how those ideas are made to persist.

**Inherit, don't restart.** The moment a rule is confirmed, the playbook editor mirrors it into a separate, read-only **seed** file — one per strategy area — that outlives any single run. Wipe the working state and start cold, and before the first turn the system rebuilds each playbook straight from its seed: *baseline plus everything ever proven*. The seed is append-only and cannot overwrite the hand-written baseline, so knowledge only ever moves forward — paid for with evidence once, and never lost again.

**Cut your losses fast.** This is the watcher's entire job. Every ten days it grades the run against the best one on record and returns one word: *on-track*, *underperforming*, or *doomed*. A "doomed" verdict late in a run ends it on the spot; earlier, when there is still runway to recover, it takes two consecutive strikes. An abandoned run fast-forwards to the end and books the loss cheaply — but the real payoff is that its dead-end ideas are marked dead immediately, instead of lingering as ambiguous noise that confuses the next attempt.

**Always build from your best day — the champion episode.** This is the mechanism that makes the whole loop safe to run, so it is worth spelling out in full.

Every episode produces a complete **plan**: the day-phased checklist plus the coordinator's and specialists' strategy summaries. At the moment it is written, that plan is snapshotted verbatim to disk as the *current* plan. Around it runs a small, deterministic, runner-driven checkpoint cycle — no LLM at any step:

- **Promote on a clean run.** When an episode finishes without being abandoned, its plan is promoted to the **champion** — the single best plan on record. It becomes the new reference point every future run is measured against.
- **Protect on a doomed run.** When an episode is abandoned by the watcher, the champion is left exactly as it was. A bad run cannot overwrite the best one; the wreckage is never mistaken for progress.
- **Restore before the next run.** If the previous episode doomed, the next one does not re-derive its plan from that failure — the runner reloads the champion plan verbatim, and the planner builds forward from there.

The consequence is that **a bad attempt literally cannot contaminate the next one**, because the next one was never looking at it — only at the champion. Rollback is not a special case that needs handling; it is a plain file copy the runner performs on its own, without ever asking a model.

Note the two persistence layers this creates, deliberately kept separate. Individual *rules* accrete forward through the seed mirror; whole *plans* are checkpointed and reverted through the champion mechanism. One preserves hard-won facts; the other preserves a coherent overall strategy. A run can lose the second without ever losing the first.

## Results

Same models. Same code. The only thing that changed across attempts was the memory the network wrote for itself.

| Attempt | Cumulative reward |
|---|---|
| 0 | 12,121 |
| 1 | 9,226 |
| 2 | 31,406 |
| 3 | 119,575 |
| 4 | **331,642** |
| 5 | 195,812 |

That is roughly **27× from attempt 0 to attempt 4**, with no weight updates and no human touching the prompt in between. The steepest gains land exactly where the system locks in its core money-maker — research-gated ride upgrades paired with a high-rating concessions loop — and writes it down where it cannot forget it again.

It is not a straight line up, and we want to be upfront about that: attempt 5 fell back to 195,812. That is what genuine exploration looks like, and it is precisely the case the champion mechanism exists for — attempt 6 plans from attempt 4's peak, unaffected by attempt 5's stumble. The system also never reached the target we set going in. It climbed; it did not arrive.

## Limitations

This is a proof of concept, not a leaderboard result: one system, one benchmark, six attempts, one model family, no baseline comparison, and no error bars.

The single real point of failure is that the system's judgment is only as good as its telemetry. If the metric can be gamed or the log is lossy, it will learn the wrong lesson with total confidence. That is not a footnote — it is the actual precondition for this pattern to work anywhere, and the reason an external benchmark with a deterministic score is the right place to test it.

And the causality is correlational, not proven: a rule is judged by whether a metric moved while it was live, not by a controlled experiment. Demotion — the playbook editor's ability to remove a previously-learned rule — catches some of the false positives that slip through, but not all of them.

## The takeaway

Bigger models will raise the starting point. But an agent that cannot trust its own memory does not get better simply because the model underneath it does. A self-improving agent network is what you get when you take that seriously: memory that must prove itself before it is trusted, a judge that only believes the log, deterministic guardrails so the actor cannot grade its own homework, the willingness to abandon a lost run early, and always starting the next attempt from the best day it has ever had.

*A case study, not a claim of generality — read the numbers as evidence that something is possible, not as a benchmark to beat.*
