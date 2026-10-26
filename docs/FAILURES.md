# Failure analysis

`tools/failure_analysis` answers three questions about an eval: why each
rollout failed, which skills each model lacks, and which failures the reward
can teach. It reads any verifiers `traces.jsonl`, so it works on future evals,
not only the hard2 runs.

**Deterministic first.** Every label carries the evidence that produced it.
A model labels only the residual cases that rules cannot classify. That step is
opt-in, recorded and replayable, and its labels never affect a reward. The
grader's verdict is always the one in the trace.

## Layers

| layer | what | for | determinism |
|---|---|---|---|
| 1 root cause | one category per failed rollout, with evidence | every failed rollout | rules on the trace |
| 2 event logs | submission and formal gold rerun with an event monitor; first divergence | `miss`, `self_check_failed`, `never_finishes` | simulation, recorded |
| 3 residual label | one label from a model that is not evaluated | the layer-2 set | `--label-residual`, recorded, `--replay` |
| 4 task features | pass@1 joined with witness depth, mechanisms, module | every task | proposer run files |
| 5 RL views | pass@k, learnability, fix channel, tokens | every graded rollout | arithmetic |
| 6 validation | blind hand-check sample; `--agreement` | sample | seed 0 |

**Infrastructure.** Rollouts with no grade (provider error, sandbox failure),
Verilator internal errors and compile timeouts are `infra`. They are excluded
from every rate and listed separately in `summary.md`. Verilator internal errors
are toolchain bugs to report upstream.

## Layer 1: taxonomy

Rules are tried in this order. The first that applies decides.

| category | rule | evidence | sub-label |
|---|---|---|---|
| `infra` | no `info.grade`; or `%Error: Internal Error` in a compile error; or `compile_timeout` | stop condition and error; the internal-error line | `no_grade`, `verilator_internal`, `compile_timeout` |
| `budget` | blank submission, and the last call ended with `finish_reason: length` (max_tokens) or the agent timed out | finish reason, output tokens, max_tokens | `max_tokens`, `agent_timeout` |
| `empty_answer` | blank submission, and the model stopped on its own (no limit hit) | finish reason, tokens, whether `module tb … endmodule` is in the reply or the reasoning | `malformed_fence`, `answer_in_reasoning`, `no_answer` |
| `policy_violation` | grade status `policy_violation` | the policy message | the message |
| `illegal_stimulus` | grade status `illegal_stimulus` | the `ILLEGAL_STIMULUS:` line (rule, time, checker instance) | the rule |
| compile family | grade status `compile_error`: the **first fatal `%Error` line in log order** decides, using the rules below | the line, the submission's source line, how many fatal errors and of which categories, PINMISSING pins | see below |
| `never_finishes` | status `timeout` or `no_finish` | status, run seconds | the status |
| `self_check_failed` | `runtime_error` with a `%Fatal`/`%Error` line from `tb.sv` (the testbench's own `$fatal`, `$stop`, `$error`) | the testbench's message and line | `watchdog` (message says timeout/never/waiting), `check` |
| `runtime_crash` | `runtime_error` with no such line (the simulator itself died, e.g. a `forever #0` loop) | run seconds | — |
| `miss` | status `ok`, a target not hit | target hits, other plan items hit | — |

The compile family, applied to that first fatal line:

| category | rule | sub-label |
|---|---|---|
| `literal_bitselect` | `syntax error, unexpected '['` and the source line indexes a sized literal (`8'hA5[i]`) | — |
| `unsupported_construct` | `%Error-UNSUPPORTED`, any `Unsupported:` message (unclocked assertions, mixed blocking/non-blocking), or `syntax error, unexpected void` | the message, `void cast` |
| `undeclared` | `Can't find definition of variable` | the name |
| `assign_to_input` | `%Error-ASSIGNIN` | the signal |
| `include_path` | `Cannot find include file` | the file |
| `interface_hallucination` | `%Error-PINNOTFOUND` (pin or parameter); evidence names the instantiated module and its real ports | the pin |
| `other_syntax` | any other compile error; the first error line is kept | the message without names; `decl_after_statement`, `top_module_missing` |

### Known blind spots

- **The first fatal error decides.** Cascades are rare because Verilator stops
  after the parse pass, but two independent elaboration errors (e.g. a missing
  pin and an undeclared variable) are both real. `categories_in_log` records
  every category in the log.
- **Diagnostics are a 4000-character tail** (`closure_core.sim.LOG_TAIL`). A
  long compile log can lose the first errors, so the first error seen is the
  first one kept.
- **PINMISSING is a warning** under `-Wno-fatal` and never fails a compile by
  itself. It is kept as evidence (`pinmissing`), never as the cause.
- `literal_bitselect` needs the source line. An unexpected `[` without a sized
  literal on that line is `other_syntax`.
- `interface_hallucination` finds the module as the nearest line above the pin
  that starts with a design module name. An instance written on one line
  after other code, or a module name in a comment, can mislead it.
- `decl_after_statement` is inferred from the message
  (`unexpected IDENTIFIER, expecting "'{"`) and a source line that starts with
  a type keyword. The rule doesn't check that a statement comes first.
- `self_check_failed/watchdog` is a keyword match on the testbench's own
  message.
- `empty_answer/malformed_fence` covers replies whose code fences the
  taskset's extractor (last fenced block) reads as empty. Seen: a doubled
  opening fence.
- A `runtime_error` whose run log is empty falls back to the compile log in
  the grade. Only a `%Fatal`/`%Error` line *at* `tb.sv` counts as a self-check,
  so compile warnings on `tb.sv` cannot be mistaken for one.

### Empty answers: the what-if

For `answer_in_reasoning` and `malformed_fence`, the testbench is taken from
the reasoning or the reply. It is the last fenced block holding `module tb`
(the taskset's rule), else the last `module tb … endmodule`. That testbench is
graded offline through the same executor and grader. The result is reported
separately (`summary.md`, `evidence.whatif`). It is a likely serving or format
issue, and the official score never changes.

## Layer 2: event logs

For `miss`, `self_check_failed` and `never_finishes`, both the submission and
the task's formal gold (`designs/<d>/gold/<ID>.sv`) are rerun in the task image
recorded in the trace, through an Executor (`--executor prime` in practice).
Nothing else is rerun. The run uses `closure_core.grader.simulate`, the same
file layout and the same legality rules as the grader. Appended to the
testbench is a monitor bound to `uart_rx` and `uart_tx`, never to the
testbench. It logs one line per event:

    <cycle> <time> <rx|tx> <event> <value>

- **cycle** counts clock posedges since reset was last high, so testbenches
  with different reset lengths are comparable.
- **Events:** `hs` (an AXI-Stream handshake, value = data), `frame_error`,
  `overrun_error` (each cycle high), `busy_rise`/`busy_fall`, and `prescale`
  (when it changes, and at the first cycle out of reset).
- Logging stops after 4000 lines. Lines are flushed one at a time, so a
  testbench killed at the timeout keeps its log.

**First divergence:** the first event in the gold's log that the
submission's log lacks (`missing`) or has at another cycle
(`at a different cycle`, with the submission's cycles). Because a different
prescale shifts every cycle, `sequence` also gives the first gold event the
submission lacks *in order, ignoring cycles*. When `sequence` is null, every
gold event occurs in order at other cycles.

The replay's own status is recorded (`evidence.replay`, `matches_trace`) but
never replaces the trace's verdict.

Blind spots:

- The rx byte appears only on a handshake. In targets with `m_axis_tready`
  held low (overrun tasks), the logs show the error pulses but not the word
  held on `m_axis_tdata`.
- A gold is one witness. A submission can reach the target by another route,
  so a divergence is not a fault by itself.

## Layer 3: residual labels (opt-in)

`--label-residual` asks `anthropic/claude-opus-5.5` (not an evaluated model;
temperature 0; recorded in the run manifest and every record). The prompt
gives the task description, gold, submission, both event logs (the first 150
lines each) and the first divergence. It asks for one label and one sentence
that cites log lines:

| label | meaning | fix channel | skill axis |
|---|---|---|---|
| `timing_arithmetic` | right shape, wrong cycle arithmetic | reasoning | timing arithmetic |
| `wrong_sequence` | right frames, wrong order or count | reasoning | multi-frame sequencing |
| `wrong_data` | right sequence and timing, a data value differs | reasoning | spec reading |
| `protocol_misunderstanding` | wrong AXI-Stream or UART semantics | knowledge | protocol knowledge |
| `near_miss` | matches the gold up to the last step, misses by one condition | reasoning | timing arithmetic |
| `misread_spec` | drives a different scenario from the target | reasoning | spec reading |
| `wrong_self_check` | plausible stimulus, wrong check or wait condition | reasoning | spec reading |
| `unclear` | evidence does not support one label | — | unattributed |

An answer that does not parse as one of these is recorded as `unclear`. Every
call is saved as `runs/failures/<run-id>/labels/<key>.json`, holding the
messages, the parameters and the response. `--replay` rebuilds every label
from these records with no model call. A record is reused only if the
messages are identical, the same rule `tools/propose_plan` uses.

Residual labels are **indicative only** until `--agreement` reports accuracy
and Cohen's kappa of at least 0.8 against the hand labels. `summary.md` says
which applies.

## Fix channel and skill axis (fixed mappings)

| category | fix channel | skill axis |
|---|---|---|
| `literal_bitselect`, `unsupported_construct`, `undeclared`, `assign_to_input`, `include_path`, `other_syntax`, `runtime_crash` | compiler feedback | syntax and Verilator subset |
| `interface_hallucination` | compiler feedback | interface knowledge |
| `illegal_stimulus` | knowledge | protocol knowledge |
| `policy_violation` | instruction following | spec reading |
| `budget` | budget | budget management |
| `empty_answer` | instruction following | answer formatting |
| `miss`, `self_check_failed`, `never_finishes` | reasoning, refined by the residual label | the residual label's axis; without one, *unattributed* |

The mappings live in `FIX_CHANNEL` and `SKILL_AXIS` in the tool.

## Layer 4: task features

For each task, pass@1 per model is joined with the proposer run's witness
measures from `summary.json` (witness frames, active frames, input changes),
keyed by candidate through `written.json`. It is also joined with the
mechanisms in `plan.yaml`, which must equal `summary.json`'s, and with the
module, the cover's `bind` target. Tables show pass@1 by mechanism, by depth
bucket (witness frames < 1.9, 1.9–2.0, ≥ 2.0) and by module. They are
descriptive only: 26 tasks cannot support significance claims.

## Layer 5: RL views

- **pass@k** for k = 1, 2, 4, 8: the unbiased estimator
  1 − C(n−c, k)/C(n, k), averaged over tasks with at least k graded rollouts.
  The gap between pass@1 and pass@8 is the headroom RL can sharpen.
- **Learnability:** for each category and model, failures on tasks with mixed
  outcomes (the reward can teach these) against failures on tasks at 0 of k
  (curriculum or other help needed).
- **Fix channel** counts per model.
- **Success by output-token quartile** per model, with the budget and
  empty-answer count in each quartile.

## Layer 6: validation

`results/failures/handcheck.csv` is a stratified random sample (seed 0):

- 5 rollouts per layer-1 category (all, when a category has fewer);
- 20 from the residual set;
- every residual of a model with fewer than 20 residuals, too few to judge a
  labeller on a sample.

Rows are shuffled and carry evidence and log excerpts but no predicted label.
`handcheck_key.json` maps each sample to its strata. Fill in `hand_category`
and `hand_residual_label`, then run `--agreement`. It reports precision per
layer-1 category, and the labeller's accuracy and Cohen's kappa. Rerun
`--replay` to put the result into `summary.md`.

## Outputs

`results/failures/` (git-ignored, like all of `results/`):

- `labels.jsonl`: one row per failed rollout, with model, task, category,
  sub-label, evidence, residual label, fix channel, skill axis and log paths;
- `summary.md`: counts, category per task and model, skill gaps, RL views,
  task features, infrastructure, empty answers;
- `handcheck.csv` and `handcheck_key.json`;
- `exemplars/<category>/<model>.md`: one per category and model, the rollout
  with the median submission length (lower median; ties by task, then key).
  Each has its evidence, the gold excerpt, and, for layer-2 categories, both
  event logs and the first divergence.

`runs/failures/<run-id>/` records the run: `manifest.json` (trace paths and
sha256, proposer run, git commit, executor, labeller), `sim/in` and `sim/out`
(every layer-2 and what-if job and result), `events/` (logs), and `labels/`
(model calls).

## How to rerun

    # layers 1, 2, 4-7 (simulations in Prime sandboxes, in the task image)
    tools/failure_analysis ../cb-probe/outputs/official/*/*/traces.jsonl \
        --propose-run ../cb-run-hard/runs/propose/20261026T095426Z-hard2 \
        --written ../cb-probe/runs/propose/20261026T095426Z-hard2/written.json \
        --executor prime --concurrency 8 --tag hard2-official
    # layer 3 on the same run (recorded batches are reused, not rerun)
    tools/failure_analysis --resume runs/failures/<run-id> --label-residual
    # rebuild every output: no model call, no simulation
    tools/failure_analysis --replay runs/failures/<run-id>
    # after hand-labelling
    tools/failure_analysis --agreement results/failures/handcheck.csv
    tools/failure_analysis --replay runs/failures/<run-id>

The Prime executor and the labeller need the verifiers and openai packages and
`PRIME_API_KEY`. `--executor docker` runs the task image locally. Tests:
`pytest tests/test_failure_analysis.py`.
