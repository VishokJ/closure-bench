# closure-bench: appendix

Details behind [REPORT.md](REPORT.md). Section references like 3.2 point to the main report.

## A. The environment in verifiers

closure-bench is a verifiers v1 taskset. Each task is one coverage target; a harness produces a testbench; and the reward is computed in a separate, isolated grading sandbox.

- **Task.** `ClosureTask` carries the design, the target IDs, the harness and a simulation timeout. The taskset loads one task per plan item that has a proven-reachable gold. An `items` list selects a subset, such as the 26 hard tasks; multi-target and per-module campaign modes are also built.
- **What the agent sees.** The RTL, the existing testbenches and the cover files. Also the coverage-report entry for its target (0 hits), a plain-English description of the target, the cited datasheet pages, and the protocol rules it must follow.
- **Harnesses.**
  - `null`: one model reply, from which the testbench is extracted. This is the reported setting.
  - `bash`: a shell with Verilator and a `run.sh` that grades any testbench, so the agent can iterate.
- **Runtime.** Prime sandboxes from a toolchain image pinned by digest. The image holds Verilator 5.020 and nothing else: formal tools would solve the task. The agent's sandbox can reach only the model endpoint.
- **Isolated grading.**
  - `setup` writes the repo into the agent's sandbox; `finalize` records the submission.
  - Scoring runs in a fresh, offline sandbox: only `submission/` is restored, `stage_verifier` installs the grader bundle, and the `grade` metric runs it.
  - The agent's sandbox never contains the grader, the golds or the near-misses.
- **Reward and metrics.**
  - Reward: `target_reached` (weight 1) is 1 if the simulation finishes cleanly and the target is hit.
  - Metrics say why a rollout failed: compiled, policy violation, illegal stimulus, finished, target hit, simulation time, turns and tokens.
- **Validation.** `vf-validate --only-gold` runs every gold through the same isolated path and must score 1; `--only-noop` (an empty testbench) must score 0.

## B. Pipeline steps in full

1. **Propose (target only).** Stage A lists N target ideas. Stage B writes each one as three things:
   - a cover module, the condition as code;
   - a twin, a nearby condition that must not count;
   - a plain-English description.

   Each target declares at least two difficulty mechanisms (appendix C).
2. **Static gates.** Cheap checks that run first (appendix D).
3. **Formal witness.** Yosys searches for input stimulus that reaches the cover under the protocol rules. The witness must be at least 1.5 UART frames deep and is written out as a testbench: the gold. The twin's witness becomes a near-miss (appendix E).
4. **Simulation gates.**
   - The gold must score 1 in the real grader, and the near-miss 0.
   - The existing tests must miss the target.
   - Grading must be deterministic.
   - The target must have value (appendix F).
5. **Set stage and write.** Accepted tasks are re-gated in order against the growing pack, which catches two tasks that are really one behaviour. Writing into the repo first replays the whole recorded run, and refuses if any decision differs.

Infrastructure errors, such as a sandbox that fails to start, never count as decisions: the run retries, then stops, rather than silently rejecting a task. Gates run in parallel Prime sandboxes with shared caches. The 26-task run took 1.5 hours; 10 candidates failed their first attempt, mostly on depth, and all 10 were repaired.

## C. Difficulty mechanisms

Each target must declare at least two of these mechanisms. The last column counts how many of the 26 hard tasks use each.

| Mechanism | What it adds | Example | Tasks |
| --- | --- | --- | --- |
| Boundary | a cycle-exact window: the event must land on a specific clock | T9: data sampled exactly at bit boundaries, at prescale 2 | 25 |
| Data | specific byte values, so a mistimed frame cannot hit by accident | R26: 0x3C, then 0xA5 | 22 |
| Sequence | events in a fixed order across frames | R26: frame error, then overrun | 19 |
| Interaction | two features at once | R25: a stalled byte accepted in the middle of the next frame | 12 |
| Reset timing | behaviour in the first clocks after reset (at most 2 per run) | T7 | 2 |

Depth is the sixth axis, enforced for every task: the formal witness must be at least 1.5 frames long.

## D. The gates before formal

Cheap static gates run first, so a malformed or misleading target never costs a formal search. Each exists because we saw the failure it catches.

| Gate | Rule | Failure it catches |
| --- | --- | --- |
| format | the reply parses into a cover, a twin, a description and a plan entry | truncated or malformed replies |
| cover_sync | exactly one cover point with the task's label, in the named module | plan and cover files out of step |
| cover_policy | the cover uses only allowed constructs (checked on Verilator's syntax tree) and one `bind` into a design module | a cover with logic of its own that fakes a hit or ends the simulation |
| description_sync | every signal and constant the description names is read by the cover; a declared but unused port does not count | a description that promises more than the grader checks (models gamed this with unused ports) |
| mechanism | at least two declared difficulty mechanisms; at most two reset-timing targets per run | single-trick targets; a flood of near-identical reset tasks |
| citations | every source verifies: an anchor string on the pinned lines of the RTL or README, or on exactly one page of a hash-checked datasheet | invented or misplaced evidence |

No gate uses a model. A citation either verifies or it does not, and a cover either reads a signal or it does not.

## E. The formal gate in full

Formal search now does the solving the proposer used to do. That removed the difficulty cap, and it also gave us a difficulty measure, legal golds and near-misses for free.

- **What it does.** Yosys (abc `bmc3`) searches up to 300 clock cycles from reset for any input sequence that makes the cover true. The sequence it finds, the witness, is written out as an ordinary testbench: the gold. A target with no witness is rejected as unreachable.
- **No cap from the proposer.** The proposer only has to describe a target precisely, not hit it. A target can be harder than anything the proposer could write a testbench for, as long as it is reachable.
- **A difficulty measure.** The witness is a shortest path to the target, so its length is a floor on any solution. We measure it in UART frames (10 bits on the wire), not raw cycles. Our first floor, 160 cycles, was gamed by padding with stall cycles and a slower baud rate. The floor is 1.5 frames; hard tasks run 1.8 to 2.9.
- **Legal by construction.** The protocol rules the grader enforces (4.2) are formal's assumptions, so every gold uses stimulus a real system could produce.
- **Near-misses for free.** The twin's witness must score 0 on the real target. That shows the cover is no looser than its description.
- **Engineering.**
  - Most early "timeouts" were spent minimizing the witness, not searching for it (about 820 of 900 s); minimization now has its own 180 s budget.
  - Witnesses are cached across runs.
  - The pipeline image and the agent's image share an identical Verilator binary (619 of 619 simulations matched), so a gold that passes in the pipeline passes in grading.

## F. Value: mutation testing and cited requirements

A reachable target is not automatically a useful one. Every task must show value: its gold catches a bug the existing tests miss, or the task checks a requirement the documentation states.

- **Mutants.** We make 203 copies of the design, each with one small planted bug: a flipped comparison, an inverted condition, a constant off by one, a signal stuck at 0 or 1, or a dropped statement. A test **kills** a mutant if it passes on the real design and fails on the mutant.
- **What the existing tests miss.** They kill 127 of the 203. The other 76 are bugs the regression cannot see. They go into the proposer's context as hints, and the first pipeline's golds killed 69 of them.
- **The value gate.** A task passes if its gold kills a surviving mutant, or if it cites a verified requirement from the datasheet or README.
  - We chose not to make mutation a hard gate. A one-line mutant cannot stand for a missing feature or a multi-step timing bug, so "kills nothing" is absence of evidence, not evidence of no value.
  - Spec-only tasks are the first to audit, because a citation can be real yet not support the claim.
- **Formal golds.** A witness only reaches the target; it checks nothing, so it kills no mutants. The 26 hard tasks pass the value gate on cited requirements.

## G. Calibration and the ladder

We generate at maximum difficulty and step down only on evidence. A hard task can be relaxed mechanically, but an easy one cannot be made hard without starting over.

**Calibration** works at three levels:
1. **The set.** The trainable model's mean pass@1, with a target of 0.3 to 0.6, plus its failure mix and the number of tasks with mixed outcomes. A binary reward gives the most signal per task near 0.5; a task at 0/8 or 8/8 teaches nothing.
2. **Each task.** A beta-binomial estimate, with more rollouts for unclear tasks, then a bounded harden or relax.
3. **The report.** Fresh rollouts on models whose results selected no task.

**The ladder.** A mechanical composer builds harder targets from accepted ones, with no model call:
- A then B within N clocks;
- the k-th occurrence of A;
- A and B on the same clock;
- A without B ever since reset;
- A within N clocks of reset, with N set by formal's minimum.

Each composed target has lower rungs (a looser window, then its parts). A task that proves too hard can step down to a sibling that has already passed the gates. The ladder is built but paused: the generated set landed in range without it.

**What happened on the hard set.** We calibrated on Nemotron 3 Nano first: 10% at k=2. Enforcing the protocol rules (4.2) dropped it to about 6%, too sparse to train on. So instead, since we had legitimately hard tasks, we moved the trainable model to Qwen 3.8-27b, which lands near the band. That is model selection on aggregate results, not task selection: no task was kept or dropped on any model's results, and the official k=8 runs are fresh data.

## H. The testbench policy, exploit by exploit

The grader compiles the design, our cover module and the agent's testbench, runs the simulation, and reads one counter: how often our cover point fired. A testbench is supposed to change only the design's **inputs**, the way a real system around the chip would. Every exploit below reaches the counter some other way, and each is now rejected before or during grading.

An analogy: a driving test where the examiner only checks that the car reached a certain street. The honest way is to drive there. The exploits are ways of making the checklist say "reached" without driving.

| Exploit | In plain words | Analogy | Blocked by |
| --- | --- | --- | --- |
| `force` on an internal signal | overwrite a wire inside the design directly | teleport the car | policy check, before simulation |
| hierarchical write (`tb.dut.state = 3`) | set an internal register from outside | move the odometer by hand | policy check |
| driving an output port, or binding code into the design | make the design's outputs or internals do what you want | sit in the examiner's seat | policy check |
| redefining `uart_rx` | submit your own simpler copy of the design; Verilator silently keeps whichever definition it sees first | bring a car that is already there | redefinitions rejected |
| fake coverage | declare your own cover point with the same name, or drive our cover module's inputs directly | forge the checklist | provenance: only our cover, bound under the real design, counts |
| `$system`, file I/O, inline C | shell out, or write a fake coverage file | bribe the examiner | policy check; grading sandbox is offline |
| parameter overrides | reconfigure the design | change the rules of the test | banned |

A violation ends the rollout with status `policy_violation` and reward 0. In the official runs, models almost never tried these: 1 attempt in 621. The reward hacking we did see was subtler, and it came through the inputs.

## I. Failure analysis: skill axes per model

| Skill axis (failures) | Nemotron (192) | gpt-6-sol (33) | Qwen (67) |
| --- | --- | --- | --- |
| Syntax and the Verilator subset | 75 | 26 | 14 |
| Interface knowledge (ports that don't exist) | 35 | 0 | 0 |
| Protocol knowledge (handshake rules) | 26 | 1 | 16 |
| Timing arithmetic | 23 | 6 | 11 |
| Multi-frame sequencing | 10 | 0 | 0 |
| Spec reading | 16 | 0 | 7 |
| Budget (never committed to an answer) | 0 | 0 | 14 |
| Answer formatting | 3 | 0 | 4 |
| Unattributed | 4 | 0 | 1 |

- **Nemotron mostly can't produce a testbench that compiles.**
  - 33 of its 35 interface errors invent a `busy` pin on the combined `uart` module, which has `tx_busy` and `rx_busy` instead.
  - 34 of its syntax errors declare a variable halfway through a block, which SystemVerilog forbids.
  - Most of its failures are on tasks it never solves, so the reward alone cannot teach them.
- **gpt-6-sol has one slip and a little timing.** All 26 syntax failures are the literal bit-select (section 5); 6 of its 7 misses are timing. All are on tasks it sometimes solves.
- **Qwen has a real mix, and almost all of it is teachable.** All 15 illegal-stimulus failures, 12 of 14 budget failures and 9 of 13 misses are on tasks it sometimes solves.

Across models:
- **Receiver vs transmitter flips.** gpt-6-sol is perfect on transmitter tasks and loses points on receiver tasks (the syntax slip). Qwen is the reverse: 73% on receiver tasks, 55% on transmitter tasks, because of the handshake.
- **Longer thinking doesn't help Qwen.** Its pass rate is flat (0.69 to 0.71) across output-length quartiles until the longest, which drops to 0.62, where 15 attempts ran out of budget or left an empty answer.
- **Deeper targets are harder for the smaller models.** At 2 frames or more, Qwen falls from 0.73 to 0.54 and Nemotron to 0. With 6 such tasks this is descriptive only.

## J. Qwen's failures in full

Grouped by what went wrong rather than by grader status, Qwen's 67 failures come down to four causes.

| Root cause | Attempts | In plain words |
| --- | --- | --- |
| Misreads when the receiver acts | 20 | It assumes things happen at the end of a bit; this receiver acts in the middle |
| Counts instead of watching the handshake | 15 | It predicts when the transmitter will be ready instead of waiting until it is |
| Never commits to an answer | 18 | It writes the testbench, keeps revising, and runs out (14) or leaves it inside its thinking (4) |
| Syntax slips | 14 | Grammar errors: 7 are the literal bit-select |

**Misreading when the receiver acts (20).** The serial line works like Morse code: each bit lasts a fixed beat, and this receiver listens in the middle of each beat, not at its end. Qwen's picture of the design has it acting at the end. Calculations on that picture are exact and still wrong. The 20 attempts are grouped by hand, checking each model label against the event-log lines it cites:

- **The phantom byte** (7 attempts, on R26, R13 and R29). To send a byte with a broken stop bit, Qwen holds the line low for the whole beat.
  - The receiver checks mid-beat and flags the error, then sees the line still low and decides a new byte is starting.
  - Its count is now out of step, so the next real byte is garbled and the target never happens.
  - It is like holding a Morse key down through the pause between letters. gpt-6-sol makes the same mistake on R26.
- **The early reply** (7 attempts, on R20, R22, R18, R28 and R14).
  - The receiver hands over a finished byte in the middle of the last beat. Qwen's sending routine keeps transmitting until the beat ends, then starts waiting for the byte, which was already delivered and taken.
  - The wait hangs and Qwen's own watchdog kills the run. It is like finishing a sentence on a walkie-talkie, then listening for a reply that came while you were still talking.
- **Glitches that miss the receiver's listening point** (3, R15). A transmitter frame counted as 80 cycles instead of 81, plus one other transmitter timing slip (2, T6 and T11). One byte sent with its bits in the wrong order (1, R25).

The design's code is in the prompt. Qwen reasons from a textbook picture of a UART instead of reading this design's timing.

**Counting instead of watching (15).** Handing a byte to the transmitter means holding it out until the transmitter says it is ready.
- Qwen predicts the ready moment by counting clock ticks, holds the byte out for one tick at that moment, and lets go. When the count is off, it lets go before the hand-off: the shortcut of 4.2.
- **13 of the 15 never wait for the ready signal at all.** Qwen even writes the rule in its own comments.
- The existing transmitter testbench in its prompt has a correct routine (`axis_send`) that keeps holding until ready is seen, and Qwen writes its own counting version anyway.
- 21 of its 35 transmitter hits also count; they pass only because the arithmetic happened to be exact.

The robust habit: count to decide when to start holding the byte out, if the task needs a precise moment, but watch to decide when to let go.

**Never committing (18).**
- **All 14 attempts that hit the 65,536-token limit contain 2 to 6 complete testbenches inside the thinking.** In one R26 attempt the right fix is already there: a short low pulse, then a gap so the receiver does not restart. It then spends its last tokens tidying a redundant line, and never answers.
- These cluster on the hardest tasks (T9, T12, R26, T6).
- The 4 empty answers are the same failure: a finished testbench left inside the thinking. Grading those 4 offline recovers no hits, so the score is not understated.

**Syntax slips (14).**
- 7 literal bit-selects;
- 2 declarations in the middle of a block;
- 2 unsupported `void` casts;
- 3 one-offs.

## K. Training plan: order of work and guard metrics

Order of work:
1. **Before training.**
   - **Scale the task set.** 26 tasks would overfit within a few steps; train on hundreds, holding out whole task families.
   - **Fix the environment:** extract a testbench left in the thinking, count Verilator crashes as infrastructure, and add the commit rule.
   - **Run `tools/failure_analysis` on every checkpoint,** so these categories become training curves.
2. **Warm start.** Rejection-sampling fine-tuning on Qwen's own legal, concise successes, plus the DPO minimal pairs for the handshake and the syntax idioms. This clears format and syntax noise, so the RL signal goes to reasoning.
3. **Main loop: RLVR.** GRPO with dynamic sampling (drop groups that are all wins or all losses, the same filter as our mixed tasks) and overlong shaping, with the binary reward unchanged.
4. **Hard tail.** Ladder curriculum and the annealed progress reward for tasks at 0 of 8.
5. **Agentic RL in the bash harness.** Running the simulation replaces simulating the chip in its head, which attacks the timing misconception and the budget burn at once.

**Guard metrics** throughout, watched for reward hacking:
- illegal-stimulus and policy-violation rates;
- output length;
- **self-checks per testbench.** 7 of Qwen's 20 reasoning failures were its own checks firing, so RL will find that deleting watchdogs and assertions raises reward. Checks must not decay, and the mutation score of the agent's testbench (L.3) is the eventual fix.

## L. Next steps in full

#### L.1 More designs: what we look for

The pipeline is generic. Per design it needs a pinned RTL pack, a few cited documents, a `legality.yaml` and a formal search configuration. Good next designs have:
- **More state and more interaction**: several interfaces, queues or arbitration, so that targets need longer and more interleaved sequences than a UART allows.
- **A citable specification for their interfaces**, so legality rules and value requirements come from documents, not from our judgment.
- **A size bounded search can handle**, or a structure that splits into blocks verified separately.
- **Low memorization risk**: recent or little-known code with a permissive license.
- **An existing regression**, so coverage holes and surviving mutants define where the tasks are.

#### L.2 Scaling the pipeline

- **Grading cost.** About 7–9 s per grade, mostly compiling C++. That's fine for evaluation, but a bottleneck for RL throughput. Compiling the design and cover once per task and linking only the testbench per rollout would cut most of it.
- **Formal cost.** Bounded search grows with depth; 300 cycles covers about 3.7 frames at the fastest baud rate. Deeper targets need k-induction, abstraction of wide counters, or chained witnesses that start from intermediate states.
- **Generation throughput.** One run produced 26 tasks in 1.5 hours on parallel sandboxes. Shared caches already make repeat work nearly free; the next gains are seeding new runs with prior ideas and stopping searches early on targets that are provably unreachable.
- **Audit at scale.** Gates remove the mechanical errors; a sampled human audit, weighted towards spec-only tasks, should measure the error rate that remains.

#### L.3 Harder tasks

- **Deeper witnesses.** Raise the frame floor as formal scales.
- **Composed targets.** Use the ladder's tops (sequences, counts, crosses, exclusions, reset budgets) as tasks, with their lower rungs as built-in relaxations.
- **Multi-target and campaign tasks** (built, not reported): one testbench must close several targets, or every target of a module, scored as a fraction.
- **Targets from surviving mutants**: the bugs the whole plan still cannot catch.
- **Closure under a budget**: the bash harness with a cap on simulations, so efficiency matters.
- **Open-ended closure**: the agent reads the coverage report and chooses what to close, closer to the real job.
- **Checking, not only reaching**: score whether the agent's testbench would catch bugs (its mutation score), first as a metric, then as part of the reward.

#### L.4 Calibration and training

- **Bash-harness evals on the same 26 tasks.** The harness is built (a shell, Verilator and `run.sh`, which grades any testbench). Expect the syntax slips to disappear and the frontier model to near-saturate; the open question is whether simulating, instead of reasoning about timing, fixes Qwen's misreads. Report tokens, turns and cost next to pass rates, and add a simulation budget so the agent cannot simply search.
- **Per-task calibration and an easier tier** for small models like Nemotron: beta-binomial estimates, more rollouts for unclear tasks, and a bounded step up or down the ladder.
- **Run the training plan in 6.3 on Qwen**, starting with a short GRPO run on held-out task families. It shows whether the signal turns into improvement.
