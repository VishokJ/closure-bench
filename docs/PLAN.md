# closure-bench: verification and benchmark plan

Status: living plan. Each section says what is built and what is still to
build. "Predicted" entries are replaced by measurements as the pipeline runs.
Every decision lists the alternative, the cost, and the evidence that would
change it.

## 1. Goal

Measure, and later train with RL, an agent's ability to do coverage closure.
The agent gets a design, its existing regression and a coverage report with
holes. It must write a testbench that drives the design into one uncovered
behaviour. The UART is where the tasks live, not the thing being tested.
The contribution is the pipeline that turns a design into validated tasks;
scaling means running it on more designs.

## 2. Pipeline

```
design pack ─► baseline ─► holes + mutant survivors ─► context pack
                                                          │
                          propose_plan (LLM proposes) ◄───┘
                                     │ candidate bundles
                                     ▼
                     gates (mechanical, cheapest first) ─► accepted plan items
                                                              │
               verifiers adapter ─► pilot (2 models × k) ─► harden ─► final set
                                                              │
                                                     red-team the grader
```

| Step | Output | Deterministic? | Status |
|---|---|---|---|
| Design pack | pinned RTL, baseline TBs, `design.yaml`, `sources.yaml` + `sources.lock` | yes | built (UART) |
| Baseline | `coverage.dat`, code holes | yes | built |
| Grader | `closure_core.grader`: one function that decides the reward | yes | built |
| Gates | `closure_core/gates.py`, run by `tools/check` | yes | built |
| Mutation | fixed-operator mutants, kills per testbench | yes | built |
| propose_plan | candidate items as bundles (cover, gold, near-misses, citations) | recorded and replayable | built; smoke run next |
| Adapter | `environments/closure_bench`, one task per accepted item | n/a | built; R1 verified on Prime |
| Pilot / harden | pass@1 per task with CIs, tier moves | seeded, reported with CIs | to run |
| Red-team | exploit corpus, fixed vs open | yes | backlog in §10 |

Correctness never depends on an LLM. LLMs propose; mechanical gates decide.

## 3. Task definition

The agent gets what a verification engineer has: the RTL, the baseline
testbenches, the cover files, the coverage report entry for its target (name,
location, 0 hits) and a one-line description. It writes one SystemVerilog
testbench with top module `tb`.

Reward = 1 iff the run reaches `$finish` cleanly (status `ok`) and every
target cover point has hits > 0. Otherwise 0.

Difficulty comes from the engineering, never from hiding information.
Allowed levers: cycle-exact timing, narrow windows, deeper sequences, crosses,
multiple targets, harness (null vs bash). Not allowed: vague wording,
withholding the coverage report.

Follow-up: the upstream README is cited by plan items but not yet in the
agent's view; add it before the pilot.

## 4. Grader

- Fresh directory per run with only the pinned RTL, our cover files, our
  simulation driver (`sim_main.cpp`) and the submitted testbench.
- Fixed Verilator 5.020 flags in one place (`closure_core/sim.py`), with
  `--x-assign 0 --x-initial 0` for determinism.
- Statuses: `ok`, `compile_error`, `compile_timeout`, `timeout`,
  `runtime_error` (`$fatal`, `$stop`, crash), `no_finish` (events ran out),
  `policy_violation` (see below), `illegal_stimulus` (see below).
  Only `ok` can score.
- Coverage provenance: a functional point counts only if it comes from our
  cover file, in the plan's cover module, under the plan's label, at the
  instance our `bind` created under a real DUT instance. A testbench that
  declares its own cover with the same label, or instantiates our cover
  module and drives it, scores 0 (both tested).
- Logs go to files and only the tail is kept, so a testbench printing in a
  loop cannot exhaust grader memory.
- Testbench policy: before simulating, `grade()` parses
  the submission and runs `policy.check_testbench`. Any violation (force,
  `$system`, `$c`, file I/O, hierarchical writes, instances placed inside a
  design module) gives status `policy_violation` and reward 0. A parse failure
  is a `compile_error`; a wrong Verilator version is a grader failure.
- Legal stimulus: `designs/uart/legality.yaml` lists the protocol and spec
  rules a testbench must obey (AXI-Stream s2.8.2 TVALID low in reset, s2.2 and
  s2.2.1 TVALID held and TDATA stable until the handshake, README prescale
  nonzero where a module reads it and constant while busy), each cited. `closure_core/legality.py`
  generates from it a checker `chk_legal_<module>`, bound to each module and
  compiled with every graded testbench: a violation prints
  `ILLEGAL_STIMULUS: <rule> at <time>` and calls `$fatal`, and the grader
  reports `illegal_stimulus` (reward 0). Formal assumes the same rules, so the
  difficulty it measures is the difficulty under the stimulus the grader
  accepts. Search restrictions (prescale 1..4, reset in the first cycle) stay
  formal-only in `designs/uart/formal/`. A plan item about a documented hazard
  may allow rules (`legality: {allow: [...]}`), for formal and the grader
  alike; a multi-target grade drops a rule only if every target allows it.
  Mutation runs compile no checker (a mutant may change `busy` or
  `s_axis_tready`, which the checker reads).
- On Prime: the agent's sandbox never contains the grader, golds or
  near-misses. Grading runs in a fresh, offline sandbox where only the
  submitted testbench is restored and the grader bundle is staged.
  `tests/test_bundle.py` checks that the bundle loads on its own.

Cost: about 9 s per grade, mostly C++ compile. Fine for eval; an RL
bottleneck (reported, not solved).

## 5. Citations

Every plan item cites at least one source; tools/check verifies each one.
No RAG and no model in the loop: a citation either verifies or it does not.

| Tag | Source | Pinned by | Check |
|---|---|---|---|
| `RTL` | `third_party/verilog-uart/rtl/*.v` | commit `1b867e5` + lines | anchor string appears on the cited lines |
| `README` | upstream `README.md` | commit `1b867e5` + lines | same |
| `DOC` | external document in `sources.yaml` | URL + SHA-256 in `sources.lock` + page | hash matches; anchor (all whitespace removed, case-sensitive: PDF text drops spaces) appears on that page and no other |
| `BASE` | baseline coverage point | structured point (kind, file, line, name) | exists with 0 hits |

Documents (not vendored, copyrighted; downloaded and hash-checked):
- PC16550D UART datasheet (National Semiconductor, 1995), §8.4 Line Status
  Register: bit 1 overrun, bit 3 framing error (receiver resynchronises),
  bit 4 break; features list: false start bit detection.
- AMBA AXI-Stream, ARM IHI 0051B: §2.2 handshake, §2.2.1 data stable while
  waiting, §2.8.2 TVALID low during reset.

A source can carry `role: requirement` (what the design must do) or the
default `role: evidence`. Only verified DOC or README requirements count for
the value gate; RTL and BASE describe what the design does, so they cannot.

Spec ambiguity, recorded rather than resolved silently: README line 42 says
"the word is discarded" on overrun. The RTL (uart_rx.v:123-125) overwrites the
unread word, so the old word is lost, which matches 16550 §8.4 bit 1. Tasks
follow the RTL; the report notes the wording.

## 6. Validity gates

A plan item becomes a task only if it passes every gate. Gates are plain
functions of simulation results (`closure_core/gates.py`), so `tools/check`
runs everything in parallel and `gate_candidate` runs them cheapest first,
stopping at the first failure.

| Gate | Rule | Failure it catches |
|---|---|---|
| `cover_policy` | cover file uses only allowed constructs (AST of `verilator --xml-only`), one `bind` to a design module with `.*` | a cover with logic of its own that fakes a hit or ends the run |
| `description_sync` | every design signal and sized/hex constant the description names is read by the cover (same AST; a declared but unread port does not count) | a description that promises more than the grader checks |
| `citations` | every source verifies (§5) | invented or misplaced evidence |
| `cover_sync` | exactly one cover with the item's label, in the named module | plan and cover files out of sync |
| `baseline` | no baseline testbench hits the item | free tasks |
| `gold` | the gold testbench scores 1 | unsolvable tasks |
| `near_miss` | at least one near-miss per item (opt-out only with a written, audited reason), and every near-miss scores 0 | a cover looser than the description claims |
| `determinism` | grading the gold twice gives the same result | flaky rewards |
| `value` | gold kills a baseline-surviving mutant, or a verified requirement source | items that are reachable but do not matter |
| `duplicate` | some testbench hits this item and not the other, for every other item | two items that are one behaviour |

Golds are self-checking: they assert on DUT outputs, so a mutant can make
them fail. The cover alone only proves the behaviour was reached.

`cover_policy` and `baseline` split the work: the policy rejects covers that
are structurally wrong; a trivially true cover passes the policy and is
rejected by `baseline`.

Value gate, alternatives considered:
- Hard mutation gate (must kill a survivor): rejected. A kill is evidence, but
  no kill is only absence of evidence. One-line mutants cannot represent
  missing features, spec mismatches or multi-statement timing bugs, so a hard
  gate would systematically reject items that guard against them.
- Mutation or spec evidence (chosen). Spec-only items are always in the audit
  sample, because a citation can be real yet not support the claim.
  propose_plan logs every rejection caused only by `value`, which measures the
  false-rejection risk. Evidence that would change this: many audited
  spec-only items turning out not to matter.

Near-misses are required for every item rather than only for boundary or
timing items: a per-item label deciding whether they are required would be
under optimization pressure from the repair loop (relabelling is the cheapest
repair). Opt-outs are counted in the funnel.

Random-stimulus probe: fixed-seed LFSR testbenches
(`designs/uart/random/`) drive random data, bad stop bits, glitches, idle gaps,
backpressure and prescale changes while idle. Items they hit are reported as
`hit_by_random`, not rejected; they also join the duplicate corpus. A cheap,
model-free difficulty signal to compare against pilot pass rates.

Duplicate gate: an item's signature is the set of testbenches that hit it.
Identical signatures fail. Adding testbenches can only split signatures, so
the gate becomes more precise as the corpus grows. Implications (this gold
also hits item X) and identical mutant kills are reported, not enforced.

Dropped: a blind-solver gate (a second model must solve each item from the
agent view). The pilot measures solvability from the agent's view directly;
items no pilot model solves get a fairness check instead (§9).

## 7. Mutation analysis

Purpose: deterministic evidence that an item matters. Reaching a behaviour
only finds bugs if a test also checks it; mutants measure that.

- Operators over the always blocks (uart_rx.v:86-140, uart_tx.v:78-113):
  relational swap (only inside `if` conditions), condition inversion,
  constant ±1, stuck-at 0/1, dropped statement. Stable IDs
  `file:line:op:k`; no randomness.
- Kill = the testbench passes on the original RTL and its status is not `ok`
  on the mutant (a hang counts). Mutants that fail to compile (stillborn) are
  excluded. Each testbench runs only against mutants of modules it instantiates.
- Two phases: baselines against every mutant, then golds against baseline
  survivors only. Mutation runs compile without covers, so results stay valid
  when covers change. Results are cached under a hash of every compiled input,
  toolchain and platform.
- Measured (UART): 203 mutants, 0 stillborn. Baseline kills 127 (0.626).
  With R1's gold: 0.635. R1 kills `uart_rx.v:127:drop:0` and
  `uart_rx.v:127:stuck0:0`, both only by R1. 74 survivors are unexplained.
  arm64 and amd64 agree mutant by mutant.
- Survivors go into the propose_plan context pack: each one is a behaviour
  change the regression cannot see.

Equivalent mutants: a survivor that cannot change behaviour is waived in
`waivers.yaml`. A waiver claims equivalence; a kill by any testbench
disproves it, and `tools/check` reports it as a bad waiver.

Alternatives: YosysHQ MCY is the industrial option (single-netlist mutant
selection, removes the per-mutant compile). Formal equivalence checking
(Yosys/SymbiYosys) could prove survivors equivalent and auto-waive them, or
return a counterexample that seeds a new item. Not in scope: it needs an
image rebuild and bounded proofs are inconclusive on the deep counters.
Listed as an open item.

Extension (eval metric, weight 0, not reward): mutation score of the agent's
own testbench, to see whether agents check what they reach.

## 8. Plan authoring: propose_plan

R1 is hand-written and hand-checked; it is the reference bundle. Every other
item comes from `tools/propose_plan`.

- Context pack: RTL, README, cited document pages, baseline holes, the
  unexplained mutant survivors, R1 as a worked example.
- Stage A: the model lists candidate behaviours. Stage B: one bundle per
  candidate as tagged blocks (cover file, gold, near-misses, plan entry with
  citations). The model writes the placeholder `ITEM`; the tool assigns final
  IDs.
- Each bundle is overlaid on the design pack and run through the gates,
  cheapest first. On failure the gate error goes back to the model, up to 2
  repairs.
- Every model call is recorded; `--replay` rebuilds the run without calling
  a model.
- Accepted items carry provenance (`proposed_by`, prompt hash, run id,
  `status: auto_accepted`). A sampled audit, including every spec-only item,
  gives a measured error rate. Waivers stay hand-written.
- The run ends with a funnel report: candidates per stage, rejections per
  gate, repairs, acceptances, and the recall proxies below.

Recall, measured by proxy (there is no expert reference list; a list written
by a non-expert would measure agreement with that person, not recall):
1. Survivor closure (headline): baseline survivors minus waivers, split into
   killed by existing golds, killed by this run, and remaining (listed).
2. Hole closure: 0-hit line, branch and toggle points minus hole waivers,
   split into closed by the existing plan, closed by this run, and remaining.
3. Requirements cited: distinct verified requirement anchors, existing vs new.
   No "remaining" count: the documents' requirements are not enumerated.
4. Optional: Stage A with a second model family, or with the full documents
   instead of the selected pages; behaviours listed only there.

Doc pages: four pages chosen by reading the documents (16550 pp. 1, 16; AXIS
pp. 18, 28), each with a reason in sources.yaml. Requirement coverage is
relative to these pages. Automatic selection is deferred until there is more
than one design.

Proposer model: a different family from both pilot models, recorded in
`proposed_by`. Every accepted item has a gold the proposer wrote, so a
proposer that is also evaluated would be scored on tasks built around its
own abilities.

Evidence that would change this: an hour with a verification engineer
reviewing the plan would give a real reference.

## 9. Coverage plan

Verilator 5.020 does not support `##` sequences, so multi-step items use
small tracking flags or counters in the cover module plus a simple cover.
Where correctness needs data, the item requires a specific pattern (0x55,
0xA5) so a mistimed frame cannot satisfy it by accident.

Tier = predicted difficulty, replaced by measured pass rate after the pilot:
T0 anchor, T1 medium, T2 hard (cycle-exact or narrow window), T3 multi-step.

Seed candidates below were written while reading the design. Only R1 is
implemented. They are a sanity check on proposer output, not a recall
reference.

### 9.1 Receiver (uart_rx)

| ID | Behaviour | Sources | Tier | Baseline |
|---|---|---|---|---|
| R1 | Frame error | RTL rx:126-127; README:42-44; 16550 §8.4 b3; BASE rx:122 | T0 | 0 (measured, implemented) |
| R2 | False start rejected | RTL rx:112-114; 16550 features; BASE rx:109 | T0 | 0 (measured) |
| R3 | Overrun | RTL rx:125; README:40-42; 16550 §8.4 b1 | T1 | 0 (measured) |
| R4 | Shortest accepted start (low for exactly 4·prescale cycles) | RTL rx:108-111,133 | T2 | predicted 0 |
| R5 | Longest rejected glitch (4·prescale−1 cycles) | RTL rx:108-115,133; 16550 features | T2 | predicted 0 |
| R6 | Break (frame error with all data bits 0) | 16550 §8.4 b4; RTL rx:119,126 | T1 | predicted 0 |
| R7 | Held break resyncs | 16550 §8.4 b3; RTL rx:120-136 | T2 | predicted 0 |
| R8 | Recovery after frame error (next word 0x55) | 16550 §8.4 b3; README:42-44 | T1 | predicted 0 |
| R9 | Backpressure without overrun | README:52-63; AXIS §2.2.1; RTL rx:101-103,125 | T2 | predicted 0 |
| R10 | Back-to-back, zero idle | RTL rx:120-138 | T2 | predicted 0 |
| R11 | Smallest prescale (good 0x55 at prescale 1) | README:26-28; RTL rx:111,118,133 | T1 | predicted 0 |
| R12 | Largest prescale (good 0xA5 at 16'hFFFF) | RTL rx:76; README:26-28 | T1 | predicted 0 |
| R13 | Prescale changed mid-word, word still good | README:28-30; RTL rx:111,118 | T2 | predicted 0 |
| R14 | Reset mid-word, then good 0x55 | AXIS §2.8.2; RTL rx:87-95 | T1 | predicted 0 |
| R15 | Frame error with a word pending, pending word unchanged | README:42-44; RTL rx:101-103,126-127 | T2 | predicted 0 |

### 9.2 Transmitter (uart_tx)

| ID | Behaviour | Sources | Tier | Baseline |
|---|---|---|---|---|
| T1 | Reset mid-word | AXIS §2.8.2; RTL tx:79-84 | T1 | predicted 0 |
| T2 | Word completes at prescale 1 | README:26-28; RTL tx:95,104,108 | T0 | predicted 0 |
| T3 | Word completes at prescale 16'hFFFF | RTL tx:70; README:26-28 | T1 | predicted 0 |
| T4 | Prescale changed mid-word | README:28-30; RTL tx:104,108 | T1 | predicted 0 |
| T5 | Word latched while tready low | RTL tx:89-97; AXIS §2.2 | T1 | predicted covered (should be dropped by `baseline`) |

### 9.3 Multi-target tasks (T3)

Built from accepted items once single-item pass rates are known; one
testbench must close all targets. Candidates: M1 = R1 + R8 + R2 (error,
recovery, glitch); M2 = R3 + R9; M3 = R4 + R5 (both sides of the glitch
threshold).

### 9.4 Waivers (not tasks)

| ID | Hole | Reason |
|---|---|---|
| W1 | uart_rx.v:120 implicit else | unreachable: `bit_cnt` can only be 1 there |
| W2 | uart_tx.v:106 implicit else | same argument |
| W3 | `prescale[15:6]`, `prescale_reg[18:6]` toggles | trivially closed by a large prescale; replaced by R11, R12, T2, T3 |
| W4 | `prescale == 0` | `(0<<3)-1` wraps; README implies prescale ≥ 1; spec question, not a task |
| W5 | `s_axis_tvalid` high during reset | illegal stimulus (AXIS §2.8.2) |
| W6 | baud-rate skew tolerance | not observable inside the DUT |

W1-W3 have coverage points and go into `waivers.yaml` under `holes:`; W4-W6
have none and are recorded here only. Mutant waivers are added during survivor
triage after the proposer run.

## 10. Red-team

Fixed (a dedicated test for each is part of the exploit corpus below):
- Testbench declares its own cover with the target's label: ignored.
- Testbench instantiates our cover module directly and drives it: ignored
  (bind-site placement check).
- Output flood: logs go to files, tails only.
- Missing `$finish`, `$fatal`, `$stop`, hangs, compile errors: all score 0.
- Found by probes, fixed by the policy in `grade()` (tests/fixtures/attacks/,
  each with its pre-fix score): `force` into the DUT (scored 1), hierarchical
  write from the testbench (1), the same write from a module bound into
  uart_rx (1), a bound module driving a DUT register through an output port
  (1), redefining uart_rx or cov_R1 (0, but only because Verilator silently
  keeps the first definition, which depends on compile order). `defparam`
  into the DUT is allowed: it is equivalent to a `#()` override.

Backlog:
- `` `line `` directive to fake a cover's file path.
- `$c()` inline C++, `force` or hierarchical writes into DUT internals,
  `$system`, file I/O, writing a fake `coverage.dat`, shadow modules,
  `` `define `` tricks.
- Plan: the AST walker's testbench denylist enforced in `grade()` (above),
  plus the sandbox (offline, fresh directory, grader-owned main). An exploit
  corpus of testbenches that must score 0, run as tests.

## 11. Difficulty and calibration

Tasks are generated at maximum difficulty (target-only, formal witnesses at
least 1.5 frames deep) and stepped down only if the evidence says so. A task
with 0 < pass rate < 1 is one that gives RL signal; a binary reward carries the
most signal per task near pass@1 = 0.5.

Calibration, three levels:
1. Set: mean pass@1 of the trainable model with a task bootstrap, target
   0.3-0.6; the failure mix (truncation, compile, timeout, illegal stimulus,
   miss) and the share of tasks with mixed outcomes. Adjust the generator, not
   individual tasks.
2. Task: empirical-Bayes beta-binomial per task (too_easy, too_hard, in_band,
   unclear); +2 rollouts for unclear up to k=8; bounded harden/relax repair.
   Not run on hard2: the set level was enough to pick the models.
3. Report: fresh rollouts on models whose per-task results selected no task.

What happened on hard2 (26 items, R12-R29, T5-T12):
- Calibrated first on Nemotron 3 Nano 30B (null harness, k=2, 32k tokens):
  pass@1 0.10, failures mostly compile errors and truncation.
- Sanity runs (k=1, 65k tokens): gpt-6-sol 0.76, Qwen 3.8-27b 0.70.
- Re-graded with the legality checker (section 10): Nemotron about 0.05,
  gpt-6-sol about 0.5, Qwen about 0.48. Most lost frontier hits pulsed
  s_axis_tvalid without a handshake.
- Nemotron at about 5% gives almost no tasks with mixed outcomes, so the
  trainable model moved to Qwen, which sits in the band. This is model
  selection on aggregate results, not task selection: no task was kept or
  dropped on any model's results.

Final eval: Qwen 3.8-27b (open weights, the trainable model) and gpt-6-sol at
high reasoning effort (frontier reference, a different vendor from the
proposer, claude-opus-5.5). Both: null harness, the prompt that lists the
legality rules, k=8, max_tokens 65536, agent timeout 2400 s, provider errors
retried and any left excluded as infrastructure. Report pass@1 and pass@8 with
task-bootstrap intervals, the failure mix, the number of tasks with 1-7/8
successes, and padded vs the rest. Nemotron is reported as the calibration run.

Decision gate: if Qwen's pass@1 under the final settings falls outside
0.2-0.7, or fewer than a third of the tasks have mixed outcomes, revisit the
generator (depth floor, an easier tier) before training. A larger design
(`axis_fifo` from alexforencich/verilog-axis, or picorv32) stays the next step
for breadth.

## 12. Open questions

1. R13 (prescale changed mid-word) given the README documents it as a hazard.
   Proposed: keep; verifying documented hazards is real work, and the
   condition only requires the word to complete.
2. Multi-target scoring. Proposed: all-or-nothing reward, fraction reached
   logged as a metric.
3. Formal equivalence for mutant survivors (§7). Proposed: out of scope,
   listed as open.
