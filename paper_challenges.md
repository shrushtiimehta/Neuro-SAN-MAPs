# 3.1 Challenges and Design Responses

A self-improving agent network must change itself without changing its weights.
That single constraint defines a *substrate* of things that can change (agent
instructions, shared task memory, tool and data wiring, network topology) and
forfeits every guarantee a gradient would have supplied over it: attribution,
bounded update magnitude, monotone-in-expectation progress, and a stable identity
for the object being updated. Each challenge below is a property of that substrate
or of the network operating over it, not of any particular task. We instantiate the
method on a long-horizon business-simulation benchmark (§4) and cite that record as
evidence; the challenges are stated so that replacing the benchmark leaves them
intact.

---

## C1. Deciding what is being improved

**Problem.** "Self-improvement" is underspecified until the object of the update is
named. With weights frozen, a network can revise four distinct things: the
*instructions* each agent runs on, the *task memory* they share, the *wiring* that
determines what each agent can see and call, and the *topology* that determines
which agents exist and who owns which decision. These layers differ in granularity,
in reversibility, in how cheaply an individual change can be verified, and in blast
radius. A system that conflates them cannot state what it learned.

**Why the obvious approach fails.** Permitting one agent to revise "whatever looks
wrong" mixes a strategy revision, which is cheap, reversible and testable inside one
task run, with a topology change, which invalidates every contract in the network and
requires a new test suite before it can be scored at all. The two cannot share an
update rule, a cadence, or an approval path.

**Our solution: stratify the substrate, and give each layer its own authority and
cadence.** In our system, task memory is machine-updated every run under the
hypothesis protocol of C2; instructions are machine-updated only by promotion into
explicitly scoped sections; wiring and topology are human-authored, fixed for the
duration of a run, and changed only between runs. Each layer's updates are recorded
separately, so the paper can report which layer produced which gain.

**Evidence.** The stratification is not merely tidy, it is the paper's most
uncomfortable result. Across our development record the compounding, hands-off
improvement came from the machine-updatable layers, while the largest step changes
came from the two layers the loop could not touch: introducing per-agent observation
slices, and making a single agent the sole owner of one class of decision, which
eliminated an entire category of invalid action at the source. Reporting this
honestly sets the research agenda for automating the upper layers rather than
overclaiming that they were automated here.

---

## C2. Credit assignment is two-dimensional in a network

**Problem.** A single-agent learner must attribute a task outcome across time. A
network must attribute it across time *and* across agents. The space of candidate
causes is the product of turns and agents, while the observable signal remains one
scalar per run, and the outcome is jointly produced: a coordinator selecting among
specialists' proposals means a good result credits both the proposal and the
selection.

**Why the obvious approach fails.** Per-agent self-report is not evidence; an agent
asked what it contributed will answer. Nor can attribution be recovered from the
final score, since a successful run is equally consistent with one decisive decision
and with ninety-nine irrelevant ones. Long horizons make this worse rather than
better when the reward compounds: in our instantiation the mean ratio of final to
mid-run score across 139 complete runs is 10.0x, and the mid-run score predicts the
final score at only r = 0.688, so no early quantity is a usable proxy.

**Our solution: constrain the network until attribution is decidable, then test
hypotheses rather than infer causes.** Exactly one action is committed per turn, and
every action is logged deterministically together with the agent that proposed it,
the validation verdicts it passed, and the resulting metrics. A candidate improvement
enters memory not as an observation but as a falsifiable hypothesis: a *rule* (a
general instruction, not a one-off), a *success condition* naming a metric, a
direction and a window long enough that a single lucky step cannot fake it, and a
*failure condition*. Each hypothesis is scoped to one domain, and therefore to one
agent, so a verdict attributes to that agent's instructions. Grading happens at the
end of the run, against the deterministic log rather than any agent's account, and is
performed by a different network than the one that acted. At most three hypotheses
are open at once, bounding how much of one outcome must be attributed simultaneously.

**Evidence.** Of 265 judged hypotheses, 51% were falsified and 9% confirmed. We read
this as the protocol working rather than failing: absent a gradient, elimination is
the attribution a single terminal score can actually support, and a loop that only
ever confirms is not testing anything. The residual problem is the *generator*, not
the grader: hypothesis coverage was heavily skewed across agents (115, 89, 80, 68, 36,
14 and 1 hypotheses across the seven agents) while the winning configuration's edge
came from two of the least-sampled ones. Sampling agents in proportion to leverage
remains open.

---

## C3. A textual substrate has no update algebra

**Problem.** Parameter updates compose, are bounded in magnitude, apply at a defined
scope, and target an object with a stable identity. Natural-language instructions and
memory have none of these four properties, and each absence produces a distinct
pathology rather than merely lower quality. *Identity*: two paraphrases of one lesson
are different objects, so a rejected idea can return under a new wording.
*Arity*: a rule carries no trigger rate, so an under-specified rule fires on every
turn. *Scope*: a text edit can rewrite anything in the file, including the reference
material the learning process depends on. *Lifetime*: durable facts about the
environment and a plan for one run have opposite retention requirements, and a single
memory conflates them, so reverting a failure also reverts what it discovered.

**Why the obvious approach fails.** "Let the agent write down what it learned" treats
prose as if it had these properties. In our record each missing property produced a
concrete failure: a rejected hypothesis returned under fresh wording across five
consecutive runs, producing no verdict in any of them; a rule with no cap or ratio
consumed 31% of one run's entire action budget; a promotion that matched a unique
string anywhere in a file overwrote hand-authored reference text, and the loss
propagated into ten archived snapshots including two best-ever configurations, so
restoring the best configuration restored the corruption with it.

**Our solution: supply the algebra in the harness.** The three-part hypothesis of C2
gives an update a stable identity and an explicit trigger condition, making it
checkable and retirable. An append-only ledger gives it history, so a falsified idea
is recorded rather than merely discarded. A cap on concurrent hypotheses bounds
update magnitude. Writes are section-scoped: a promotion may edit only below a
designated header, so learning cannot rewrite the reference block it reads from.
And memory is split by lifetime into three channels: a *fixed reference* that never
changes and is the same source of truth the deterministic validators compute against;
*learned rules*, durable and append-only, each tagged with the run that confirmed it;
and a *run plan*, rewritten at the start of each run and immutable within it. Because
the channels are separate files, a failed run's plan is discarded and rolled back
without a single learned rule going with it.

**Evidence, including what is unsolved.** Two pathologies persist. 37% of hypotheses
were never applied, because their preconditions were written too narrowly for a
stochastic long-horizon run to reliably exercise, and an unapplied hypothesis
consumes a slot and returns no information. And identity remains only partially
solved: the ledger prevents the *same* idea returning but not a paraphrase of it,
because prose cannot be deduplicated by construction. Both are reported as open.

---

## C4. Local improvement breaks joint contracts

**Problem.** Agents in a network communicate through conventions that live in prose:
a field name, a marker token, an assumed output schema, a protocol another agent is
presumed to implement. Improving one agent's instructions can therefore invalidate a
convention a different agent depends on. Nothing type-checks a prompt against its
consumers, and the resulting failure is silent, because the downstream agent receives
something plausible rather than an error. This challenge has no analogue in
single-agent self-improvement.

**Why the obvious approach fails.** Any per-agent improvement loop optimizes each
agent against a local objective, and a convention is a joint property of two or more
agents, so no local objective can detect its breakage. Nor does the task score
reveal it: a broken handoff degrades performance smoothly rather than failing.

**Our solution: move every load-bearing contract out of prose and into code.**
Cross-agent handoffs pass through coded tools with explicit schemas rather than
through free text. Each field has exactly one owning agent, so no two instruction
sets can specify the same value and drift apart. Validation applies to the composed
action rather than to each agent's contribution, and runs before the environment is
touched, so a violated contract costs one re-prompt and nothing else. Shared
reference data is read from a single file that both the model and the deterministic
validator consume, so the model's judgment and the code's arithmetic cannot disagree.

**Evidence.** Every instance we found was silent and was discovered by reading the
network rather than by running it: an instruction branch keyed on a marker token that
the harness never emitted and so could never fire; a required protocol parameter
invented on every call because no agent implemented the protocol it belonged to; the
same constant maintained in two places; a tool description advertising a limit its
own caller's instructions contradicted. We recommend, and only partly implemented,
promoting these checks to startup assertions over the network definition.

---

## C5. A lesson must reach the agent that can act on it, and only that agent

**Problem.** In a network, learned knowledge is not global. A rule is actionable only
in the context of the agent that decides the thing it constrains, and that agent is
frequently not the one whose outcome revealed it. Broadcasting every lesson to every
agent reconstitutes the undifferentiated context the network was built to avoid;
routing too narrowly strands the lesson where nothing can use it.

**Why the obvious approach fails.** A shared lessons file read by all agents restores
a single large context, forfeiting the cost and focus advantages of decomposition and
degrading each agent's precision. Per-agent memory instead requires an ownership
decision for every lesson, which is a judgment the loop must make and can get wrong.

**Our solution: one memory artifact per agent, an explicit ownership decision at
promotion time, and matched scoping of memory and evidence.** Each agent reads its own
instruction file and its own slice of the task observation, so what an agent is told
and what it can see have the same scope. Cross-cutting direction goes to the
coordinating agent only. Ownership is assigned when a hypothesis is written, not when
it is confirmed, which is what makes the verdict attributable under C2.

**Evidence.** Mis-scoped routing does not announce itself. An agent given an
instruction about something its instruments do not report will not error; it will
generalize. Our mid-episode analyst was directed to identify an available capability
while holding no tool that reported availability, and produced vague trend-based
assessments, which is the only output that instruction admitted. Routing must
therefore be validated against each agent's actual instruments, which is the
*reachability* invariant of C7.

---

## C6. Improvement is non-monotonic, so the update rule must select rather than accumulate

**Problem.** A network of stochastic components is itself stochastic, and several such
components compose, so run-to-run variance is larger than for a single agent. A run
can therefore be worse than its predecessor through sampling alone, with nothing
wrong in the memory it inherited. Any learner that carries its most recent state
forward performs a random walk over the substrate, and one bad run can destroy
progress accumulated across several good ones.

**Why the obvious approach fails.** "Reflect on the last run and update" is the
default reflective-agent loop, and it is precisely the rule that propagates a
sampling failure into the next run's starting point. Averaging is not available
either, since two textual configurations cannot be interpolated.

**Our solution: elitist selection over an archive.** A configuration is promoted only
if it clears a hard floor *and* beats the best score on record; every subsequent run
starts from the best-ever configuration rather than the most recent one. Promotion is
a deterministic file operation performed by the harness with no model in the loop, so
it cannot be argued out of the decision, and archiving occurs only on promotion, so
the archive is a record of best-ever states rather than of every boundary. This makes
the loop a select-and-archive search over textual configurations rather than a
sequential update.

**Evidence.** The mechanism is observable working: in the published sequence a
high-water mark was followed by a substantial regression, and the following run,
planned from the preserved peak rather than from the dip, set a new record. We also
report the cost: always starting from the best-known configuration prevents
regression and suppresses exploration, and our runs converged on a single structural
solution and stopped varying it. Selection pressure and diversity maintenance are the
obvious next lever and we did not implement one.

---

## C7. The improver is itself an agent network

**Problem.** Self-improvement is recursive: the component performing the improvement
is the same class of non-deterministic component being improved. Two consequences
follow, and they pull in opposite directions. First, the improver needs the same
architectural affordances as the actor. Treating it as a single call that reads a log
and returns a verdict makes it structurally incapable of causal analysis, and the
deficit does not close with a larger model, because the binding constraints are its
observation space, its tool budget and the number of passes it is allowed. Second,
the improver's failures are silent. It can quietly no-op, assert a verdict it did not
derive, grade its own work favourably, or reason correctly from corrupt evidence, and
the system has no vantage point from which to notice.

**Why the obvious approach fails.** Prompting for rigor does not produce it: an
instruction to cite evidence is satisfied by any citation. An actor evaluating its own
run has no structure separating a good outcome from a good account of one. And a
reviewer fused into the acting network shares its context, so a degraded diagnosis
contaminates the next action directly; our first architecture did exactly this, and
the two halves talked past each other at substantial token cost.

**Our solution, in two parts.** *Give the improver real affordances:* reflection is
decomposed by role and timescale rather than run as one reviewer, and each reflective
network receives deterministic telemetry tools, direct state reads, and a scratchpad
that carries a note forward to its own next pass, so a diagnosis can be built over
several looks instead of asserted in one. Its evidence channel is instrumented for
attribution rather than reused from the actor, and lossy convenience digests are
disqualified as grading evidence, since a digest that drops arguments, metrics and
idle turns renders an action that was proposed and refused indistinguishable from one
never attempted. *Constrain its authority:* the actor never grades itself; the
networks share no conversation and coordinate only through files; every irreversible
transition (promotion, retirement of stale hypotheses, restoration of the best-known
configuration, pre-dispatch validation) runs in code with no model in the loop; and
authority is bound by construction rather than chosen, so which network an agent runs
in determines what it is permitted to write.

**Evidence.** The failures this structure exists to catch were invisible from inside
the system and detectable only from outside it. A reset path deleted two state files
whose only writers live inside the passes that read them; this occurred five times,
and every run afterwards executed with a frozen plan and no learning loop at all
while appearing entirely normal, with no possible recovery because the failure mode
is "read a file that only I write". Separately, the environment resets on its terminal
step, and recording that observation as the run's final row reported a run that ended
well as having collapsed; every conclusion drawn from the final quarter was therefore
inverted across twenty runs of stored history, and remained plausible because one
metric channel keeps counting past the reset. We draw a general design obligation
from this rather than a warning: a harness that owns the learning must assert
invariants over its own loop, specifically *liveness* (was the substrate in fact
updated this run), *sanity* (does terminal telemetry agree with the penultimate
step), and *reachability* (does every instruction name a tool able to answer it).

---

## C8. When an improvement may be applied

**Problem.** Improvement between runs is well-posed but arrives after the entire
budget is spent. Improvement within a run can still change the outcome but is
ill-posed, because by C2 it cannot distinguish a failing configuration from a sound
one that has not yet compounded. The two regimes also compete for authority over the
same substrate.

**Why the obvious approach fails.** Both extremes are defective. Purely post-hoc
improvement cannot intervene and pays full price for a run it has already diagnosed.
A single reviewer intervening periodically patched symptoms with no view of the run's
arc and replaced strategies before any could prove out, which is why we cap
concurrent hypotheses at all.

**Our solution: separate cadences with exactly one authority each.** The actor decides
per turn. A mid-run analyst runs at fixed intervals and may log small course
corrections but may *not* revise the plan. The between-run planner alone sets
direction. The plan therefore runs strictly forward, keeping each run a clean test of
one configuration while preserving a correction channel that cannot silently redefine
what is under test.

**Evidence, with a caution.** The regimes interact destructively when the mid-run
authority may terminate the run. Hypotheses written to be tested late in the horizon
met an early-termination heuristic firing just before that window and surrendering
the remainder to no-op actions; this is the direct mechanism behind the 37% of
hypotheses that never fired in C3. Removing that authority raised mean score from
339,091 (n=61) to 808,173 (n=12). We flag this as a natural experiment rather than a
controlled ablation, since other changes landed in the same revision. The mechanism
generalizes independently of the effect size: where task reward compounds, an
early-termination rule must be judged against a *trajectory-shaped* baseline, the
best-known configuration's own score at that same point, and not against a terminal
target. Every one of our 139 runs, the eventual best among them included, sat below
such a terminal floor at the midpoint.

---

## C9. Evaluation cost bounds the improvement operator

**Problem.** Improving a network means scoring candidate configurations, and each
score costs a full task run. Variance (C6) means several runs per candidate before a
difference is credible. The number of configurations testable per unit budget is
therefore smaller than gradient-based search by orders of magnitude, and this is a
constraint on the *method*, not merely on the experiment.

**Why the obvious approach fails.** Random or exhaustive search over instruction space
is unaffordable at one full task run per sample. This is the structural reason the
improvement operator must be hypothesis-driven and high-prior rather than
exploratory, and the reason C2's protocol spends a scarce slot on a falsifiable claim
rather than on a variation.

**Our solution: make the run cheap, and spend the savings on samples.** Agent history
is trimmed to the current turn, which makes each agent stateless and thereby *forces*
every durable fact onto disk where another network can read it, so the cost control
and the memory architecture of C3 are the same decision. Prompt caching is applied to
the system message and tool definitions only, deliberately omitting the per-call
message-prefix breakpoint that a loop of this shape never reuses. The observation is
sliced per agent (C5) so no agent reads the whole world, and only the currently
relevant portion of the plan is surfaced. All mechanical work, meaning arithmetic,
syntactic and legality validation, and dispatch, runs in code, so the model is invoked
only where judgment is required.

**Evidence.** A hundred-turn run with seven agents costs roughly $30-40 and 12-15M
tokens, which is what made a 139-run record affordable at all. The converse bounds
our own programme: at that price a controlled ablation is a several-hundred-dollar
commitment, which is why the causal claims we make are limited to those in C8.
