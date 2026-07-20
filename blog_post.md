# Self-Improving Agent Networks: Getting Better at a Task Without Changing a Single Weight

AI agents are already capable of a great deal on their own. We wanted to see how far that can go. We're looking to build one that runs a business, an agent system that invents ideas, tests them, backs the ones that hold up, and is judged on the one thing it can't fake: does it make money? The long game is bigger: a system that reinvests what it earns into new ventures and eventually runs the whole portfolio itself, all of that by using **neuro-san-studio**, our multi-agent framework. But a grand vision is easy to write down. Does it actually work?

We can't answer that on a real business with real money: the tuition would be ruinous, and most of the early lessons are ones a simulation could teach for free. What we needed was a **simulation world that reacts to your decisions**: somewhere a run is cheap, repeatable, and honestly scored, where the business is knotty enough that the right move is genuinely unclear. So we went looking for a world simulator that fit, and found one.

You are handed an amusement park and one decision a day. Build a roller-coaster; hire a janitor; place a souvenir shop; pour cash into research. You commit a single move, the gates open, guests stream in, and by closing time the day's takings tell you how you did. Do that for a hundred days, and make the park worth as much as you can. That is **Mini Amusement Parks (MAPs)**, a business-simulation benchmark from Skyfall AI ([arXiv:2511.15830](https://arxiv.org/abs/2511.15830)), and it is genuinely hard: humans still beat the best LLM agents by roughly 10× on the **medium** difficulty we run, where only the cheapest attractions start unlocked and everything stronger is gated behind research. That gating forces a tricky balance: you have to spend on research, which pushes the park into losses in the short term but pays off later. These early foundation decisions compound over a hundred days, so a weak opening quietly caps how good the ending can get. In that way, it mirrors an actual business: every dollar a ride earns is capital to put back in, whether into a stronger ride, another shop, or more research. It's the same earn-and-reinvest loop behind our bigger vision, just scaled down to a single park. 

But there is a fundamental limit. Point an LLM (or a network of them) at MAPs, run it a hundred times with the same prompts, and the hundredth attempt is no better than the first, sometimes worse. The model is non-deterministic, and each entire game is a hundred separate decisions. With no training to build on, a strong run comes down to luck or the model's innate knowledge, not a strategy it tested and confirmed, and we don't even know whether the profits can be repeated. Either way, nothing improves across attempts: the model can neither identify which decisions worked nor carry them into the next run. An LLM is frozen at training time, and so is any agent network built from one. A bigger model raises the starting point of every attempt, but never lets the network improve *across* it.

So we built a **harness** around the models: deterministic scaffolding that turns a network of agents into a system that learns from its own runs, keeps what works, and gets better with each attempt, with no weight changes and no human in the loop. Built on neuro-san-studio, the system reached **the #1 spot on the AI leaderboard**.

![neuro-san-studio holds the #1 spot on the MAPs AI leaderboard](images/AI_Leaderboard.png)

Here is how it works.

---

# Implementation

## Running the park: the agent network

![The player agent network](images/maps_park.png)

We don't point a single LLM at the game. The park is run by an **agent network** organized with AAOSA on neuro-san-studio, looping once per day across the hundred-day game. On each turn, a coordinator (the front-man) reads the park's current state and fans a query out, in parallel, to a set of **domain specialists**, one per vertical: rides, shops, staff, layout, research, and guest-survey analyst. Each specialist can read (but not edit) its own **strategy playbook** and the slice of park state relevant to its vertical, and from those it hands back two candidate actions for its area. The coordinator reads its own playbook, weighs the candidates against the strategy written there, and picks one action. Before the action gets fired, we run two deterministic gates to check if the proposal is valid or not. 

The first gate is **`FinanceGate`**, a coded tool that does the arithmetic LLMs are unreliable at: the one-time build cost against the cash on hand, the daily operating cost, and whether the investment can still earn itself back in the days that remain, all computed from the game's economics tables, never estimated by a model. The player *proposes* an action; the gate returns a flat approve or reject.

The second gate, **`ProposeAction`**, checks the approved action against the game's rules *before the simulator advances at all* and writes the validated proposal to disk. If it's malformed or against policy, the environment is left untouched and the player is re-prompted with the reason. Only once it is written to the disk does the **loop** pick up that proposal and fire the step through **`ActionDispatcher`** coded tool. Keeping the gates and the firing in code, not the model, guarantees exactly one clean step per turn and spends no tokens on the mechanical work: the LLM is called only for the decision itself.

A loop that long could get expensive fast, six agents a turn, a hundred turns, each otherwise dragging its whole history along. So every agent is wrapped in **middleware** that trims the chat back to just the new message each turn and caches the static system prompt so it isn't re-billed on every call. The player ends up *stateless by default*: it remembers nothing between turns except what the harness has written to disk. That keeps a run cheap, and it forces a discipline the whole design leans on: the acting network has no private memory to hoard, so anything worth keeping has to be written down to disk where the rest of the system can read it, because the player isn't the only network at work.

All of that is enough to *play* MAPs. None of it makes the next run any better than the last.

## Three minds

To improve across runs, the agent network has to reflect: record what worked, discard what didn't, and carry the rest into the next attempt. We tried a few arrangements before settling on the current one. Our first version folded the reviewer into the same network as the player, and it bled tokens: the two halves talked past each other, turn after turn. Splitting them made each sharper about its own job, far cheaper to run, and let us control in code exactly when the reviewer runs. A second lesson followed: a single reviewer checking in every ten days kept patching symptoms with no sense of where the whole run was headed, and it churned through too many strategies at once, swapping them out before any had the time it needed to prove out. So we split *reviewing* in two: a between-runs **planner** that sets the direction, and a mid-run **watcher** that course-corrects against it. We also limit the number of strategies tried at 3 in one run.

So the result is three separate agent networks, each a mind with its own goal and its own timescale. No two share a conversation; to keep token use low, they coordinate only through plain-text files on disk:

- **The player.** The network described above - it plays one action a day from the context it's given, and never looks back.

- **The planner.** Runs before and after each run. At **episode start**, it compares the **best run ever recorded** against the most recent one, works out which strategies worked, which didn't, and what to carry forward, then writes the plan the next attempt will follow: a day-phased checklist plus a short strategy brief for the coordinator and each domain specialist, along with up to three fresh strategies to trial. The player re-reads that plan every turn. At **episode end**, it does a thin close-out: promoting the trials that proved out and retiring the ideas that stopped paying off.
![The planner network: a macro orchestrator with episode-start and episode-end agents.](images/planner_network.png)

- **The watcher.** Runs every ten days, at steps 10, 20, … 90 of the episode. It reads the run's telemetry so far, diagnoses the profit trajectory, and logs small course-corrections (micro-trials) the specialists act on next turn, checking that the planner's strategies are actually landing without duplicating them. It also judges one thing: is this run still worth finishing? If there's no plausible path to the target by day 100, it calls the run doomed and the loop aborts it early instead of wasting steps.
![The watcher network: a mid-episode analyst with its telemetry and trial tools.](images/watcher_network.png)

## Never losing ground: inheritance and the champion episode

Proposing plausible ideas is the easy part; the real work is making sure a good run's gains survive a bad one. Everything so far happens *within* a run. What happens *between* runs is what actually compounds, and it comes down to keeping what's proven, cutting what's hopeless before it costs much, and always starting the next attempt from the best the system has ever managed.

Each specialist's **strategy playbook** is really two layers. Underneath is a read-only **seed**, the hand-written baseline the system only ever copies from and never writes back to, so a fresh playbook always begins clean. On top of it sit the rules that trials have confirmed, promoted into the working copy the specialist reads each turn. That's what makes a playbook part fixed baseline and part living strategy that grows from one run to the next. But the memory that truly carries across runs is the **trial ledger**: every rule that's been on trial, its pass/fail criteria, and an append-only record of each verdict. It accumulates and is never wiped when a new run starts, so a falsified idea stays dead instead of sneaking back as a "new" proposal three runs later, and a confirmed one waits to be re-applied rather than rediscovered from scratch.

Cutting losses is the watcher's job. Every ten days it grades the run against the best one on record and returns a single word: on-track, underperforming, or doomed. A doom late in a run ends it on the spot; earlier, with time still to recover, it takes two strikes. And once a run is written off, there's no point burning tokens to finish it, so the runner fast-forwards to the end with empty `wait()` moves, books the loss cheaply, and marks that run's dead-end ideas dead right away, before they can muddy the next attempt.

The last piece is the one that makes the whole loop safe to run: the champion. Every episode produces a full plan, the day-phased checklist plus the coordinator's and specialists' strategy summaries, snapshotted to disk the moment it's written. A small deterministic checkpoint cycle turns around it, with no model involved at any step. A run that finishes clean and beats the best score on record becomes the new champion. A run the watcher abandons leaves the champion untouched, so wreckage never overwrites progress. And before the next run begins, if the last one doomed, the runner reloads the champion verbatim and the planner builds forward from there.

The payoff is that an abandoned run simply cannot drag down the next one, because the next one never looks at it, only at the champion. That matters most because the benchmark is noisy: plenty of runs crater for reasons that have nothing to do with the strategy, a bad streak of breakdowns, an unlucky mix of guests, and without the rollback the system would cheerfully "learn" from that variance and talk itself out of a plan that was working fine. The champion caps the cost of a lost run at a single episode, and none of it needs special handling; the rollback is just a file the runner copies on its own.

Two kinds of memory fall out of this, kept deliberately apart. Individual rules move forward through the trial ledger and the playbooks they feed; whole plans are checkpointed and reverted through the champion. One preserves hard-won facts, the other a coherent overall strategy, and a run can lose the second without ever losing the first.

## Earning memory: the falsifiable trial protocol

No lesson is kept just because a run went well. Two things make "it worked" untrustworthy: we put several strategies on trial at once (usually three), so a good result never says *which* of them earned it, and any single good result might just be luck. So the system isn't allowed to declare victory. There's a quieter failure mode underneath everything so far. If the *same* model both makes a decision and does the bookkeeping (totals the budget, estimates whether a ride will ever pay for itself, edits its own playbook), then it is grading its own homework. The numbers its judge later reads are numbers its actor could have fudged, and a self-graded memory is worth nothing. Every idea it wants to keep must first be framed as a **falsifiable hypothesis** in three parts:

1. **A rule:** a general instruction, not a one-off observation.
2. **A success condition:** a specific metric, a direction, and a **window** of days to check it over, long enough that one lucky or unlucky day can't fake the result.
3. **A failure condition:** the exact result that would prove the rule wrong.

The rule lives in one file, its success-and-failure criteria in a second, and every verdict in a third, an append-only **outcome ledger**. That ledger is the memory of what's already been tried: a falsified idea leaves a permanent mark behind, so it can't quietly come back as a "new" proposal three runs later.

While a trial is live, each specialist is handed its domain's active rules at the start of the episode (through an `ActiveTrials` tool), so the hypothesis genuinely steers real decisions instead of just sitting in a file. It runs for the full episode (100 days), then gets reflected upon using the deterministic log: a whole episode's worth of evidence, so the verdict reflects the rule's real effect and not the roll of a single lucky day, never the model's own account of what happened. The verdict is one of three:

- **Confirmed** → written permanently into the playbook.
- **Falsified** → removed, and logged so it's never proposed again.
- **Inconclusive** → carried forward untouched, for another trial.

Nothing graduates to "known" without first surviving a fair test it could have failed.

## Results

Same models. Same code. The only thing that changed across attempts was the memory the network wrote for itself.

| Attempt | Cumulative reward |
|---|---|
| 0 | 12,121 |
| 1 | 9,226 |
| 2 | 50,162     |
| 3 | 119,575 |
| 4 | **331,642** |
| 5 | 195,812 |
| 6 | **483,019** |

That's a **nearly 40× climb from attempt 0 to attempt 6** (12,121 → 483,019), with no weight updates and no human touching the prompt in between. The biggest jumps come once the system locks in its core money-maker: research-gated ride upgrades paired with a high-rating concessions loop, written down where it can't forget it again.

![Two runs of the same park, days 10 to 99: early run (left) vs best run (right).](images/run_comparison.png)

The gap is really about research. The early run spends little and places few rides, so it actually looks richer at first, with more cash in the bank, but it never builds the capacity to grow: it unlocks only the first research tier (blue), and only for a single ride, and its value stalls near $50k. The best run does the opposite. It runs at a loss early to pour money into research, works its way through every tier (blue, then green, then red), and keeps reinvesting until the upgrades compound. In the final stretch it is clearing roughly $15,000 to $20,000 in profit a day, finishing near $475k.

<video src="images/step98.mp4" controls muted loop playsinline width="720"></video>

*The best run's park in motion on day 98.*

And it's not a straight line, which is the part worth watching. Attempt 4 set a high-water mark of 331,642; attempt 5 then slid all the way back to 195,812. That's what genuine exploration looks like, and it's the exact case the champion mechanism was built for. Attempt 6 didn't inherit attempt 5's stumble: it planned from attempt 4's preserved peak, skipped the dip entirely, and came back with a new record of 483,019. The system still hasn't caught human performance (it's climbing, not arrived), but a recovery like that is the clearest sign yet that it's the memory doing the work, not luck.

## Future Scope

This is a proof of concept. It already leads every other AI run on the benchmark, but it's still well short of human performance; closing that gap is the immediate goal. Beyond MAPs, we want to turn the same loop into a general way to *build* agent networks on neuro-san-studio, out of the same three pieces we used here: an agent network, a consultant, and a test framework. An agent-network designer generates a network along with a matching test suite; the tests run; a consultant reads the results and rewrites the prompts; and the cycle repeats until enough tests pass. Same self-improving loop, pointed at the agents themselves this time, rather than at a park.

We came to MAPs to answer a narrow question: can a neuro-san-studio agent network actually learn to run something profitable? It's a first step toward the much larger one behind this whole project: a system that generates and runs businesses on its own, funding new ventures with what it earns and, in time, managing the whole portfolio itself. A park is not a business, and a benchmark is not the world. But watching the same models, untouched, climb nearly 40× because the harness around them finally remembered what worked is the first concrete sign that the larger version is worth chasing.
