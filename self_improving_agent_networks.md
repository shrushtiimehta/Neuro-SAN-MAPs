# Self-Improving Multi-Agent Networks via Falsifiable Strategy Memory: A Case Study on the MAPs Benchmark

**Authors:** [author list] · Cognizant AI Lab

**Keywords:** multi-agent systems · self-improving LLM agents · lifelong learning · open-endedness · natural-language memory · decision-making systems

## Abstract

We describe a multi-agent LLM system that improves at a long-horizon
optimization task across repeated attempts **without any change to model weights
or human-authored prompts.** The system separates a fast *actor* network, which
plays the task, from a slower *critic* network, which reflects on the play and
rewrites a set of human-readable strategy files that the actor reads on every
turn. Learning is gated by a *falsifiable trial protocol*: a candidate lesson
becomes durable knowledge only after it survives an explicit, metric-defined
test against deterministic telemetry. On the MAPs (Mini Amusement Parks)
benchmark, cumulative reward rose from 12,121 in the first attempt to 331,642 by
the fifth — a 27× gain with the model held fixed. Improvement was non-monotonic
(one later attempt regressed), which motivates the three mechanisms we argue are
the real contribution: **carrying knowledge forward** across cold starts,
**stopping** doomed attempts early, and **renewing** each attempt from the
best-ever run rather than the most recent one. We report the setup, results, and
a candid set of limitations. This is a single-system case study, not a
benchmarked claim of generality.

## 1. Introduction

Most deployed LLM agents are *stateless* across runs. A prompt is authored, the
agent executes, the process exits, and the next invocation begins with no
memory of what worked or failed. The competence lives entirely in the frozen
weights and the static prompt. For stateless tasks this is adequate; for tasks
whose winning strategy must be *discovered* empirically rather than reasoned out
in advance, it is a hard ceiling — the agent cannot get better at the specific
problem it keeps facing.

This post reports an engineering case study of a system built to break that
ceiling. The research question is narrow and practical: *can a multi-agent LLM
system measurably improve at a hard task across repeated attempts, using only
self-authored natural-language memory, with strong guarantees against learning
the wrong thing?*

Our contributions are:

1. A concrete **actor/critic architecture** in which the two roles are separate
   agent networks on separate clocks, communicating only through legible text.
2. A **falsifiable trial protocol** that treats each candidate lesson as a
   hypothesis with pre-registered success and failure criteria, evaluated against
   deterministic logs rather than the model's own recollection.
3. A characterization of the **knowledge lifecycle** — carry-forward, stop,
   renew — as the load-bearing design levers, supported by an observed
   non-monotonic learning curve.
4. A multi-layer **guardrail** design following the principle *LLMs decide,
   deterministic code enforces.*

We are explicit up front about scope: the empirical evidence is a small number of
attempts on a single benchmark with a single model. We treat the numbers as an
existence proof and a source of qualitative insight, not as a generalization
claim.

## 2. Problem setting

The task is **MAPs (Mini Amusement Parks)**, a benchmark in which an agent
manages a theme park for a fixed horizon of 100 turns ("steps"). At each step the
agent issues exactly one action — build a ride, open a shop, hire staff, set a
research speed, or adjust a price — and the simulator advances one in-game day.
Guest arrivals scale with the park's rating; guests spend on rides and
concessions, become hungry and thirsty, generate mess, and depart if conditions
degrade. Rides break and require repair. Capital is scarce early.

The objective is **cumulative park value at step 100.** The reward structure is
strongly compounding: an asset built on day 10 earns for the remaining 90 days,
and any idle step is permanently forgone value. A single 100-step playthrough is
an *episode*; the system attempts the task over many episodes.

MAPs is a useful proving ground precisely because it stresses known LLM
weaknesses: (i) it requires *exact* arithmetic under a hard budget constraint
(affordability given daily operating cost and remaining horizon); (ii) it rewards
delayed, compounding investment over locally obvious moves; and (iii) its optimal
policy is not analytically obvious — it must be found by trial and revision.

## 3. Method

### 3.1 Overview: an actor and a critic on separate clocks

The design instantiates the classical *play → reflect → play again* loop as two
distinct agent networks:

- The **actor** (the game-runner network) plays a single episode, one action per
  step, optimizing greedily under its current strategy.
- The **critic** (two consultant networks) never acts on the environment. It
  reads the log of what happened and rewrites the actor's strategy between and
  within episodes.

The two communicate only through **strategy books** — plain Markdown files — and
never share a conversation history. This is deliberate: the actor is permitted to
be fast and locally greedy because an independent, more skeptical process always
gets the last word on what counts as a durable lesson.

### 3.2 The actor network

Each turn, a top-level `park_director` reads the park's status and delegates to a
`strategy_coordinator`, which fans out in parallel to five domain specialists —
rides, shops, staffing, research, and layout. Each specialist reads *only its own
slice* of the environment state and *its own* strategy book, and returns a short,
ranked list of candidate proposals. The coordinator merges the proposals, submits
them to a deterministic budget gate, selects exactly one approved action, and
dispatches it. The environment advances one step and the cycle repeats.

This decomposition keeps each agent's context narrow and its expertise deep: the
staffing agent reasons only about staffing and never sees the ride catalog's
detail, and vice versa.

### 3.3 The critic networks

The critic runs on two cadences:

- A **mid-episode** consultant is invoked every 10 steps. It compares the
  in-progress episode against the best episode ever recorded and emits a health
  verdict — `on_track`, `underperforming`, or `doomed`.
- An **end-of-episode** consultant runs at the start and end of every episode. At
  the start it regenerates the episode's plan from the best-ever run and retires
  stale rules; at the end it evaluates the episode's trials and commits durable
  edits.

Critically, the critic grounds every judgment in **deterministic telemetry** — a
structured, append-only per-step log written solely by the runner — rather than
the model's own narration of events. The critic learns from ground truth, not
from a possibly-confabulated summary.

### 3.4 Strategy books: the memory representation

The system's long-term memory is a set of **strategy books**, one Markdown
playbook per specialist plus a coordinator book. Each book is layered:

- A **hand-authored baseline**: founding domain knowledge, the levers each
  specialist controls, and safe defaults. This layer is permanent.
- A **"Learned rules" section** that accretes over time. Every confirmed lesson
  is appended here, tagged with the episode that earned it (e.g. `(learned
  ep4)`), preserving full provenance.
- A **regenerated strategy summary** at the top, rewritten before each episode
  from the best run so far — the current best recipe plus the specific failure
  modes to avoid.
- A **phased game plan** carried by the coordinator book: the champion run's
  trajectory distilled into a turn-by-turn checklist, so the actor follows the
  strategy proven on its best day rather than re-deriving one each episode.

Because the memory is text, it is **legible and auditable** — one can read
exactly what the system believes and why. As an illustration, the staffing book
authored the following line for itself, unprompted, after comparing two episodes:

> Mistake to avoid: under-staffing — ep3 held only 5 staff, rating sagged to
> 25-37, and modify yields were 5-10x smaller than ep4's.

The system had inferred a causal chain — *staff → park rating → the multiplier on
its highest-yield revenue loop* — and encoded it where the staffing agent reads
it every turn.

### 3.5 The falsifiable trial protocol

The mechanism that prevents self-authored memory from degenerating into
superstition is a **trial protocol** that treats every candidate lesson as a
pre-registered hypothesis. A candidate is admitted only if it specifies:

1. a **rule**, phrased as a general imperative (not run-specific trivia);
2. a **success criterion** — an observable metric, a direction, and an
   evaluation window; and
3. a **failure criterion** — the observation that would disprove it.

The trial is then inserted into the live strategy book and actually influences
the actor for an episode. At episode end, the critic evaluates it against the
logged telemetry:

- **Confirmed** — success criterion met, failure criterion never tripped. The
  rule graduates into the book's "Learned rules" section.
- **Falsified** — failure criterion tripped. The rule is removed and recorded in
  an outcome ledger of dead ends, so no future analyst re-proposes it.
- **Inconclusive** — neither fired. The trial carries over, unchanged, to be
  tested again.

Admission is further constrained (Section 3.7): candidates must be falsifiable,
non-trivial, general, and within a small active budget.

### 3.6 The knowledge lifecycle: carry-forward, stop, renew

We found three lifecycle mechanisms — not the raw learning — to be what makes the
system robust.

**Carry-forward (durable accumulation).** When a trial is confirmed, its rule is
mirrored into a read-only *seed* file in addition to the working book. This lets a
lesson survive a fully-from-scratch restart: even when working books are wiped
and reset, the next episode rebuilds from *baseline + everything ever confirmed.*
This is a ratchet — knowledge accrues only after paying for its place with
evidence, and once it has, no restart loses it. Falsified rules are retained as a
record of dead ends, so the system remembers both what worked and what did not.

**Stop (early abort of doomed attempts).** Two consecutive `doomed` verdicts from
the mid-episode critic cause the runner to abandon the episode: it ceases
soliciting the actor and fast-forwards to the horizon, booking the loss cheaply
rather than spending compute on an unrecoverable run. Beyond the compute saving,
this serves *learning hygiene*: an aborted run's trials are explicitly falsified
at close-out rather than left ambiguous, so a bad run actively teaches avoidance.
A minimum-step threshold and a two-strike grace window prevent premature abort of
a slow starter, and an unparseable verdict never triggers an abort.

**Renew (rollback by construction).** Each episode regenerates its plan from the
**best episode ever observed**, not the most recent one. Consequently a poor
episode cannot propagate its mistakes: the following episode plans against the
champion, with the poor episode's falsified trials already struck from the record.
Rollback is *emergent* — a property of always measuring against the best, not a
special-cased recovery path. Renewal also supports **demotion**: a rule promoted
on a fortunate episode that later correlates with regressions can be struck from
both the book and its seed.

### 3.7 Guardrails: LLMs decide, deterministic code enforces

The overarching safety principle is to reserve the LLM for *judgment* and use
deterministic code for anything that must be exactly right. Guardrails sit at
three layers.

**Action layer.** A budget gate performs the affordability arithmetic and returns
approve/reject with a reason; if every proposal is rejected, the coordinator
returns each specialist its reason and re-solicits until an affordable action
appears. Structural validation rejects malformed actions (illegal names, invalid
or occupied coordinates) before dispatch, and prices are auto-capped — a
model-suggested price is overwritten with the correct maximum. If no valid action
is produced after repeated attempts, the runner falls back to a no-op wait rather
than firing something broken.

**Learning layer.** Candidate lessons must be falsifiable, are capped (few active
at once, at most one per domain, none logged with too few turns remaining to
evaluate), and must be phrased as general principles rather than run-specific
values — jointly constraining the system against overfitting to a single
episode.

**Honesty and authority layer.** Agents are instructed to cite step numbers and
metric deltas for claims, to read numeric constants from reference files rather
than guess, and to ask rather than hallucinate when information is missing. Two
structural protections hold: the hand-authored baseline can never be deleted by
the loop (only learned rules are demotable), and a standing human directive
outranks the books and trials and is never overwritten by the critic. The system
may revise its own conclusions freely but cannot overrule its operator or unlearn
its foundations.

## 4. Experimental setup

- **Environment:** MAPs benchmark, single park slot, horizon = 100 steps per
  episode.
- **Held fixed across all episodes:** the LLM (identical model and configuration)
  and all system code. The *only* variable that changed between episodes was the
  self-authored strategy memory.
- **Objective / target:** maximize cumulative park value; the north-star target
  communicated to the system was $1,000,000.
- **Critic cadence:** mid-episode verdict every 10 steps; abort after 2
  consecutive `doomed` verdicts, not earlier than a fixed minimum step.
- **Trial budget:** a small number of active trials, at most one per domain, none
  admitted when too few steps remained to evaluate them.
- **Measurement:** cumulative reward read from the deterministic per-step run log
  written by the runner (the same ground-truth source the critic uses).

## 5. Results

Cumulative reward by episode, with the model and code held fixed:

| Episode | Final cumulative reward |
| ------- | ----------------------- |
| 0 | 12,121 |
| 1 | 9,226 |
| 2 | 31,406 |
| 3 | 119,575 |
| 4 | **331,642** |
| 5 | 195,812 |

The headline observation is a **27× improvement** from episode 0 to episode 4
with no weight updates and no human prompt edits. Qualitatively, the sharp
episodes 2→4 gains coincide with the system discovering and then refining its core
revenue engine — research-gated escalation of ride tiers combined with a
high-rating "modify concessions" loop — and committing that discovery to its
strategy books.

Two results are as informative as the headline:

- **Improvement is non-monotonic.** Episode 5 regressed to 195,812 from episode
  4's 331,642. This is expected of a genuine exploratory learner and is the
  motivating case for the renew mechanism (Section 3.6): because episodes plan
  from the best-ever run, episode 5's shortfall does not become the baseline for
  episode 6.
- **The target was not reached.** The $1,000,000 north star was not attained
  within the observed runs. We report this plainly; the system demonstrably
  climbs but had not, in this window, reached the stated goal.

## 6. Discussion

The results support a specific reading: the *learning* is not the hard part —
prompting an LLM to propose lessons is trivial. The hard part, and where the
engineering value concentrates, is the **discipline around** the learning. Three
design levers do the work.

First, **falsifiability converts opinion into evidence.** Requiring a
pre-registered metric and window before a lesson can be admitted is what
distinguishes a durable rule from a plausible-sounding rationalization of a lucky
run. Second, **grounding in deterministic telemetry** removes the model from the
one place it is most dangerous — adjudicating whether its own idea worked. Third,
the **best-anchored renewal** makes the whole loop tolerant of bad episodes:
without it, a single regression would corrupt all subsequent plans; with it,
regressions are simply non-events.

We also note that the actor/critic split maps onto a broad and long-standing idea
— separating a policy that acts from a process that evaluates and improves it —
realized here with natural-language memory as the medium of improvement rather
than gradients.

**A selectionist reading.** The trial protocol can be viewed as an evolutionary
loop operating over *natural-language strategies* rather than genomes or weights.
Trials supply **variation** (candidate rule mutations of the current policy);
evaluation against deterministic telemetry supplies **selection** (confirm /
falsify as a fitness test); and the seed-mirror carry-forward supplies
**inheritance** (surviving rules propagate to future episodes, including across
cold starts). Demotion adds negative selection on rules that later correlate with
regressions, and best-anchored renewal is a form of elitism — the champion is
never lost to a bad generation. Framed this way, the system is a small
open-ended learner whose units of selection are human-readable imperatives, which
makes the entire evolutionary trajectory legible and auditable in a way that
weight-space search is not.

## 7. Limitations and threats to validity

We consider the limitations central, not incidental, to an honest reading.

- **Tiny sample; not a benchmark result.** Six episodes on one task with one
  model is a case study. There are no error bars, no seeds, and no baselines. The
  numbers establish that improvement *can* occur under this design; they do not
  establish magnitude, reliability, or generality.
- **Non-monotonic and unfinished.** The curve is not monotone and did not reach
  the stated target within the observed window. We cannot claim convergence.
- **Improvement is bounded by the task's ceiling.** Self-improvement reaches
  toward the best policy the environment permits; it does not raise that ceiling.
  Any observed gain must eventually asymptote.
- **The critic is a single point of failure.** The loop is only as sound as its
  outcome signal and its telemetry. Where the objective is gameable or the log is
  lossy or biased, the system will faithfully and confidently learn the wrong
  thing. This precondition — a trustworthy, hard-to-game measurement — is the
  real gating requirement for transferring the pattern to other domains.
- **Attribution is correlational.** Trials are judged by whether a metric moved in
  a window while the rule was active; this is association, not a controlled
  intervention. A rule can be confirmed on a run it did not actually cause to
  succeed (mitigated, but not eliminated, by demotion).
- **No external comparison.** We do not compare against a static-prompt agent, a
  fine-tuned agent, or alternative memory schemes, so we cannot quantify how much
  of the gain is attributable to this specific design versus the actor
  architecture alone.

## 8. Related work

The design draws on several established lines of work; we claim no novelty over
their core ideas, only a particular synthesis.

**Reasoning-and-acting agents.** The per-turn loop in which an LLM interleaves
reasoning with tool-mediated action follows the ReAct paradigm [1].

**Self-improvement via verbal feedback.** Reflexion [2] introduced improving a
language agent across attempts by having it write natural-language reflections on
its failures into an episodic memory — the closest antecedent to our strategy
books. Self-Refine [3] and self-taught reasoning approaches such as STaR [4]
similarly bootstrap improvement from the model's own outputs. Our departure is to
*gate* what may be remembered behind a falsifiable, pre-registered criterion
evaluated against deterministic logs, rather than admitting free-form reflections.

**Lifelong skill and strategy libraries.** Voyager [5] accumulates a reusable,
inspectable skill library across an open-ended environment; Generative Agents [6]
maintain a memory stream with periodic reflection. Our strategy books play the
analogous role for *policy* rather than skills, with explicit provenance tags and
a carry-forward seed that survives cold starts.

**Actor/critic and evolutionary search.** The separation of an acting policy from
an evaluating-and-improving process is foundational in reinforcement learning [7].
The selectionist reading in Section 6 — variation, selection, inheritance over
natural-language units — connects the approach to evolutionary and open-ended
learning, a core theme of work on open-endedness [8].

Relative to these, our specific emphases are (i) the **falsifiability gate and
deterministic grounding** on what an agent is permitted to remember, and (ii) the
**carry-forward / stop / renew** knowledge lifecycle that makes the loop tolerant
of bad episodes.

## References

> Indicative references to well-established prior work; author lists abbreviated.
> Please verify and complete bibliographic details before external publication.

[1] Yao et al. "ReAct: Synergizing Reasoning and Acting in Language Models." 2023.

[2] Shinn et al. "Reflexion: Language Agents with Verbal Reinforcement Learning." NeurIPS, 2023.

[3] Madaan et al. "Self-Refine: Iterative Refinement with Self-Feedback." NeurIPS, 2023.

[4] Zelikman et al. "STaR: Bootstrapping Reasoning with Reasoning." NeurIPS, 2022.

[5] Wang et al. "Voyager: An Open-Ended Embodied Agent with Large Language Models." 2023.

[6] Park et al. "Generative Agents: Interactive Simulacra of Human Behavior." UIST, 2023.

[7] Sutton and Barto. "Reinforcement Learning: An Introduction." 2nd ed., MIT Press, 2018.

[8] Stanley, Lehman, and Clune. "Open-endedness: The last grand challenge you've never heard of." 2017.

## 9. Conclusion

We presented a multi-agent LLM system that improves at a hard, compounding
optimization task across repeated attempts using only self-authored,
human-readable strategy memory, with no change to weights or prompts. On the MAPs
benchmark it achieved a 27× improvement over five episodes while remaining
non-monotonic and short of its stated target — a profile consistent with a
genuine exploratory learner rather than a scripted one. The evidence is a case
study, and we have been explicit about its limits. The transferable lesson is
architectural: an agent gets better not by having a larger model, but by having a
memory it can trust, a critic honest enough to admit only tested lessons, the
discipline to abandon a losing attempt, and the sense to begin each new attempt
from its best day rather than its last.
