# Plan proposer

`tools/propose_plan` has a model propose new plan items (a task's cover,
self-checking gold testbench, near-misses and cited sources); mechanical gates
decide which are accepted. Correctness never depends on the model: it only
generates, and every accepted item has passed the same gates as the
hand-written R1.

**Generation is recorded, judgment is reproducible.** Everything the model
received and returned is saved. `--replay` re-runs every gate on the recorded
responses, with no model calls, and must reproduce every accept/reject
decision, every repair message sent back to the model, and the summary.

## Flow

1. **Context pack** (`tools/context_pack`, in the toolchain image): pinned RTL
   and README with line numbers, baseline testbenches and their coverage holes
   (0-hit line/branch/toggle points), existing plan items and their covers,
   `waivers.yaml`, the extracted text of the cited document pages, and the
   authoring rules (`closure_core/prompts/rules.md`). Pages come from
   `context_pages` in `designs/<d>/sources.yaml`, a human relevance choice
   with a reason per page; `--full-docs` sends every page instead. The hand
   list in `docs/PLAN.md` §4 and the seed list (§9) are **not** included in any
   prompt; they stay independent checks. The pack also records, not shown in
   the base context, what the existing plan already achieves
   (`progress_before`, with each baseline survivor's line and mutation),
   computed from the run's `base_pack`.
2. **Stage A**: one call lists candidates (`kind: task`) and waiver proposals
   (`kind: waiver`). Waivers are recorded, never accepted automatically. The
   answer is parsed strictly; on a parse failure the conversation continues
   with the error, at most 2 retries, recorded and replayed like Stage B.
3. **Stage B**: one conversation per task candidate writes the bundle, with the
   token `ITEM` where the ID goes; the tool assigns provisional IDs (`P<n>`).
   Each attempt is gated by `tools/gate_candidate` in the image with networking
   off (model-written SystemVerilog runs there). On a failure the conversation
   continues with the failing gate and its detail (including log tails), at
   most 2 retries. `-p N` (default 4) runs N conversations at once; each is
   recorded under its own candidate ID and the set stage runs afterwards in ID
   order, so decisions do not depend on which finishes first. Parallel gate
   runs share the mutation cache, which is written atomically.
4. **Set stage**: individually accepted candidates are gated again, in order,
   against a cumulative pack, so two duplicates from the same run cannot both
   be accepted.
5. **Survivor pass** (default; `--no-survivor-pass` skips it): from pass 1's
   set stage, the baseline survivors no accepted gold kills are listed with
   their line and mutation, and Stage A runs again (`prompts/survivors.md`,
   with pass 1's accepted items). The model must address every survivor once:
   a task whose gold would kill it (`targets`), or a one-line reason it cannot
   be killed (equivalent, or not observable at the ports). The parser rejects
   unknown, doubly addressed or missing survivors, which gets a repair turn.
   Reasons are recorded in the summary only, never turned into waivers. Pass 2
   candidates (IDs continue, `pass: 2`) go through Stage B and the gates as
   usual, and the set stage gates them against the base pack plus pass 1's
   accepted items.
6. **Write** (`--write`, or later `--write-from <run>`): accepted items get final IDs (`R<n>` for a bind
   on `uart_rx`, `T<n>` for `uart_tx`) and provenance `{proposed_by, run_id,
   candidate, prompt_sha, status: auto_accepted}`, are appended to the real
   pack, and the full `tools/check` runs.

**Resume** (`--resume <run>`): an interrupted run continues in place with the
model and sampling from its manifest. It re-runs the run's flow and reuses
everything recorded: a model call only if this code sends exactly the recorded
messages (otherwise it stops), gate and set results as recorded. Only the
missing steps run, and `manifest.json` gets a `resumed` entry with the commit.
It refuses changed prompt templates, and a finished run unless it has
infrastructure aborts to retry. `--replay` then checks the whole run as for
one that was never interrupted.

**Infrastructure failures are not decisions** (`closure_core/infra.py`). A
simulation that hits its compile or run timeout says more about machine load
than about the testbench, so the gates never reject on one: it is retried
once, one retry at a time per process, and a second timeout raises
`InfraError` (formal tool failures are one too). `gate_candidate` then exits 2
and writes no result. In Stage B the candidate stops, `infra/<cid>.json`
records why, and the run goes on without it: it is left out of every count
(`summary.infra_aborted` lists it), nothing is cached, and the CLI exits 2. In
the set stage the run stops instead, since later candidates are gated against
the cumulative pack and skipping one would change their duplicate decisions.
`--resume` retries the aborts; `--write-from` refuses until there are none;
a replay never compares an attempt the run did not decide, and reports an
abort of its own as such, so load can make a replay fail but never flip a
decision. In mutation runs a second run timeout on a mutant is still a kill
(a real hang, cached); on the unmutated RTL, or at compile time, it is load.
Cost: a testbench that really hangs is aborted, not repaired. Parallelism
defaults to cores - 2 (`-j`) to keep timeouts rare.

**Prime executor** (`--executor prime --concurrency N`,
`closure_core/prime_executor.py`): every gate run, context pack and
`tools/check` call gets a fresh Prime sandbox from the pinned pipeline image
(the multi-platform index `propose.IMAGE`), with networking off before anything
is uploaded, at most N at once; Stage B's `-p` defaults to N. Only `run` is
replaced, so the tools get the same arguments as in Docker, from the same
`/repo`. The upload is one tarball: `closure_core`, `tools`, `designs`,
`third_party` from the working tree, the run paths the arguments name
(candidate, base pack, the run's whole witness cache: a key includes the Yosys
release, which the host cannot compute), the mutation cache and the cited PDFs.
The witness key uses the Yosys version and source revision without the build
info (`gates.tools_release`), so a witness solved on arm64 is reused on x86_64
and the other way round. Back
come the result, new witness entries (an existing one is never overwritten) and
new mutation-cache entries (merged), so the set stage and replay reuse them. A
sandbox failure (create, upload, run, download, the 3600 s run timeout) is
retried once in a fresh sandbox, then is an `InfraError` as above; exit code 2
from the tool is one too, without a sandbox retry (the tool has retried its own
timeouts). The formal-timeout lock is per sandbox: one solve per sandbox, never
contended. `manifest.json` records the run's executor, each resume's, and under
`executors` the one that gated each candidate attempt and set-stage result.
Mutation-cache keys include the machine (`platform.machine()`), so arm64
entries from a Mac do not help an x86_64 sandbox: until one Prime call has
merged its entries back (`tools/prime_smoke` does), every sandbox reaching the
`value` gate runs the baseline mutants itself. Replay and `--resume` work with
either executor.

Every gate in a run and in its replay uses `base_pack/`, a snapshot of the
pack taken when the run starts, so a later change to `designs/` (including
this run's own `--write`) cannot change a replayed decision.

## Gates, cheapest first, stop at the first failure

`format` (blocks parse, names consistent) → `cover_sync` → `cover_policy`
(AST allowlist, `closure_core/policy.py`) → `description_sync` (every design
signal and sized/hex constant the description names is read by the cover;
same parse) → `citations` → `formal` (only without `gold.sv` or with
`twin.sv`, below) → `baseline` (0 hits;
hits by the fixed-seed random testbenches reported) → `gold` (checking gold:
no assertions, must `$fatal`; reach gold: denylist only; then scores 1;
baseline holes it closes recorded)
→ `near_miss` (at least one, each scores 0, line overlap with the gold
reported; or a written `near_miss_waiver`, which passes and is always
audited) → `determinism` → `value` (mutant or spec evidence; mutants run
against every checking gold) → `duplicate`. See
`closure_core/gates.py` for what each checks. No gate calls a model.

## Gold-less candidates and `--target-only`

A candidate without `gold.sv` gets its gold from formal:
`closure_core.formal.cover_witness(pack, cover, bound=, timeout=)` searches
for stimulus that reaches the cover under the pack's formal environment
(`designs/<d>/formal/`: `formal.yaml` with `bound` and `timeout`, and one env
file per bound module). Formal measures; Verilator judges: the witness
testbench becomes the overlay's gold (a **reach gold**, first line
`// gold_source: formal`, then its depth), and the `gold` gate must still
score it 1. Unreachable, timeout, an untranslatable cover (`UnsupportedCover`)
and an invalid one (`ValueError`) are distinct rejections; a `RuntimeError`
or missing tools is an infrastructure error, handled as above. A formal
`timeout` (the budget in `formal.yaml`) may be load, so it is retried once
while no other formal job of the run is running: every solve holds a shared
POSIX lock on `<witness cache>/.formal.lock`, the retry an exclusive one
(`lockf`; `flock` does not exclude across containers on Docker Desktop). A
second timeout is a decision, cached with `retried: true` so a replay reuses
it; the repair turn reads "target too hard to verify within the time budget:
simplify one mechanism or reduce depth".
`--min-frames F` rejects a target witness shorter than F frames, the
hardening signal: "witness is N frames, below F: make the target need more
protocol activity (a further phase or an interaction), not more waiting or a
slower prescale". A witness's length in frames (`witness_frames`) is the sum
over its cycles of 1 / `frame_cycles`, the pack's frame length at that
cycle's inputs (`designs/uart/formal/formal.yaml`: `80 * prescale`, 10 bits
of `prescale << 3` clocks), so a slower prescale never makes a target deeper.
A floor in cycles did: in a smoke run with a 160-cycle floor, all three
targets were reachable at 156 cycles (two frames at prescale 1), and the model
padded them with stall cycles, an extra word, or a forced prescale >= 2.
`witness_depth` (cycles) is still recorded. Calibration on the formal
witnesses of the 13 reachable plan items and those 3 targets: two-frame
witnesses measure 1.950-1.966 frames, one-frame ones 1.000-1.050, single
events below 0.09; `--target-only` defaults to F = 1.9 (two frames). Frames
measure elapsed time, so waiting the cover itself demands still counts: the
message discourages it, the floor does not prevent it.

A candidate may add `twin.sv`, a cover `cov_<ID>_twin` of the off-by-one
condition. Its witness becomes `near_miss/<ID>_twin.sv` and must score 0 on
the target; an unreachable twin is rejected ("boundary not exact").

Reach golds check nothing, so they never run against mutants: kills, and
mutant evidence for `value`, come only from checking golds (`$fatal`
required). A gold-less item therefore needs spec evidence. A composed item
(`composed_from`, `template`) inherits its components' verified requirements
(in `tools/check` too), and its components' testbenches as near-misses that
must miss the composite: every component near-miss, plus component golds for
`cross`, `seq` and `count`, and for `excl(A, B)` A's gold if it hits B.
`--write` stores the reach gold with its header and `gold_source: formal`
in the plan entry.

`--target-only` makes Stage B write only the plan entry, the cover and an
optional twin (`prompts/author_target.md`); the context includes every file
of the formal environment, and repair turns get the formal gate's detail.
The survivor pass is off in this mode: no reach gold can kill a survivor.
Witnesses are cached in `runs/propose/<run_id>/formal/<key>.json`, keyed by
the cover, the RTL, the whole formal folder and the Yosys version, so the
set stage and `--replay` reuse them instead of re-solving.

Every target in this mode declares `mechanism: [a, b, ...]`: at least two
distinct difficulty mechanisms, at Stage A and in the plan entry. The
`mechanism` gate checks each one on the cover where a check is cheap, and
reports every failure in one repair message: `boundary` needs a twin (or a
`near_miss_waiver`), `sequence` a tracking register of the cover's own,
`interaction` reads of two or more design signals besides clk/rst, and `data`
a multi-bit constant; `reset_timing` is declared only, so the set stage
accepts at most two targets listing it per run (`reset_timing_cap`). Outside
this mode a mechanism is optional, and one is enough. The checks are
necessary, not sufficient: a cover can carry a register and still be easy,
so `--min-frames F` (witness length in frames) is the measured difficulty signal.
`summary.mechanisms` lists the accepted targets per mechanism.

## Records: `runs/propose/<run_id>/`

| Path | Content |
|---|---|
| `manifest.json` | git commit and dirty flag, image, toolchain, model and sampling, retry limit, prompt hash, context pack hash, flags |
| `prompts/` | the prompt templates used (their hash is `prompt_sha`) |
| `context_pack.json` | everything the model was shown, as data; plus `progress_before` (the plan's progress before the run: a mutation sweep and every gold), except in `--target-only` runs |
| `progress_before.json` | `--target-only`: the same, measured by the summary step on `base_pack/` so the run starts in seconds (there is no survivor pass to show it to) |
| `base_pack/` | the design pack the run gated against |
| `responses/stage_a/<attempt>.json`, `responses/stage_a2/<attempt>.json`, `responses/<cid>/<attempt>.json` | exact messages sent, sampling parameters, response text, usage (Stage A pass 1, pass 2, Stage B) |
| `candidates.json` | parsed candidates of both passes (`pass`), per pass the Stage A error if any and (pass 2) the survivors listed, and the `unkillable` reasons |
| `candidates/<cid>/<attempt>/` | the bundle as gated (`item.yaml`, `cover.sv`, `gold.sv` or `twin.sv`, `near_miss/`) |
| `formal/<key>.json` | formal witnesses (status, testbench, depth, input changes) |
| `gates/<cid>/<attempt>.json` | every gate result for that attempt |
| `set/<cid>.json` | set-stage result |
| `infra/<cid>.json` | infrastructure abort (stage, attempt, error); removed by `--resume` |
| `written.json`, `check.json` | with `--write`: final IDs, `tools/check` outcome |
| `summary.json` | below |

Only the run that produced the shipped plan is committed (`.gitignore`
excludes `runs/propose/*`; add a `!runs/propose/<run_id>/` line for it).

## Summary

`passes.1` and `passes.2` each hold `stage_a` (attempts, final parse error),
the funnels, rejections, repair rate, accepted IDs and `progress`; pass 2's
progress starts from the plan plus pass 1's accepted items, so it is what the
survivor pass adds. `progress_total` covers both.

- `funnel_first_attempt`, `funnel_final`: proposed → passed each gate in order
  (→ set stage). Gates stop at the first failure, so each gate sees only
  candidates that passed the gates before it: read these as a funnel, not as
  independent per-gate rejection rates.
- `repair`: candidates that failed their first attempt, and how many a repair
  turn fixed.
- `rejected_solely_for_value`: candidates that passed everything except
  `value`. This is the measured false-rejection risk of that gate.
  The `near_miss` row also counts `opted_out`: passes without a near-miss.
- `near_miss_opt_outs`, `hit_by_random`: accepted candidates that are always
  audited, or that the random testbenches reach by accident.
- `witnesses`: accepted candidates with a reach gold or a twin, with their
  witness depths.
- `infra_aborted`: candidates aborted as infrastructure, with the error; they
  are in no other count until `--resume` decides them.
- `cites_outside_context_pages`: candidates whose Stage A sources cite a page
  not in `context_pages`. Comparing a `--full-docs --stage-a-only` run with a
  default one shows what the page selection costs in candidates.
- `progress`: what the accepted candidates add to the existing plan, on three
  mechanical proxies (no hand-written reference list, no judge):
  - `mutants`: baseline survivors (not waived), killed by the plan before the
    run, killed by the run, remaining;
  - `holes`: baseline line/branch/toggle holes, waived (`waivers.yaml`
    `holes`), closed by the plan's golds, closed by the run's golds, remaining;
  - `requirements`: verified `role: requirement` sentences cited by the plan,
    and new ones cited by the run (no "remaining": the documents' requirement
    sentences are not enumerated).
  These are proxies for plan completeness, not recall: a run can close every
  hole and kill every survivor with items an engineer would not write.
- `survivor_pass`: survivors listed, each pass 2 candidate's `targets` and
  `targets_killed` (whether its gold, accepted or not, killed what it claimed),
  and the `unkillable` reasons for review.
  `tools/propose_plan --summarize <run>` recomputes the summary.

## Commands

```bash
uv pip install -e ".[propose]"          # openai client
set -a; source .env; set +a             # PRIME_API_KEY (bills the key owner)
IMAGE=docker.io/vishokjcs/closure-bench-toolchain@sha256:af43bde0ec76736914394e7cfb19a778b529c6c179475143fbf70cc3b407914f  # pipeline image, arm64
tools/check                                                  # in the image first: caches docs and mutants
tools/propose_plan --image "$IMAGE" --stage-a-only --tag smoke
tools/propose_plan --image "$IMAGE" --stage-a-only --full-docs --tag smoke-full
tools/propose_plan --image "$IMAGE" --write                  # the real run
tools/prime_smoke --docker "$IMAGE"    # gold-less R1 on Prime and in Docker: timings, solve times, same gates.json
tools/propose_plan --executor prime --concurrency 16 --target-only     # gate in Prime sandboxes
tools/propose_plan --image "$IMAGE" --resume runs/propose/<run_id>       # after a crash
tools/propose_plan --image "$IMAGE" --replay runs/propose/<run_id>
tools/propose_plan --image "$IMAGE" --write-from runs/propose/<run_id>   # refuses unless
#   designs/ equals the run's base_pack and a replay reproduces every decision
```

## Limits

- Stage B candidates are gated against the pack as it was, not against each
  other, until the set stage; a duplicate pair costs a full gate run each.
- An `unkillable` reason is the proposer's claim, not a proof (formal
  equivalence checking is out of scope); it stays a reviewed note.
- Every accepted item is within the proposer's ability (it wrote a gold that
  passes). The proposer (`anthropic/claude-opus-5.5`) is not one of the
  evaluated models, so this caps what can become a task rather than biasing
  tasks toward an evaluated model.
- Replay reproduces decisions given the same toolchain and pinned inputs; it
  cannot reproduce the model's responses, which is why they are recorded.
  It reproduces them for the code at the commit recorded in `manifest.json`
  (`git.commit`; `git.dirty` says whether uncommitted changes were present):
  replaying an old run with later gate code is expected to differ wherever a
  gate changed.
- `description_sync` catches names and constants only; claims about timing
  and sequence ('exactly one cycle', 'returns to idle') are not checked. The
  cover, which the agent sees, is the binding spec.
