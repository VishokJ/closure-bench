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
   list in `docs/PLAN.md` §4 is **not** included. The pack also records, not
   shown to the model, what the existing plan already achieves
   (`progress_before`), computed from the run's `base_pack`.
2. **Stage A**: one call lists candidates (`kind: task`) and waiver proposals
   (`kind: waiver`). Waivers are recorded, never accepted automatically.
3. **Stage B**: one conversation per task candidate writes the bundle, with the
   token `ITEM` where the ID goes; the tool assigns provisional IDs (`P<n>`).
   Each attempt is gated by `tools/gate_candidate` in the image with networking
   off (model-written SystemVerilog runs there). On a failure the conversation
   continues with the failing gate and its detail (including log tails), at
   most 2 retries.
4. **Set stage**: individually accepted candidates are gated again, in order,
   against a cumulative pack, so two duplicates from the same run cannot both
   be accepted.
5. **Write** (`--write` only): accepted items get final IDs (`R<n>` for a bind
   on `uart_rx`, `T<n>` for `uart_tx`) and provenance `{proposed_by, run_id,
   candidate, prompt_sha, status: auto_accepted}`, are appended to the real
   pack, and the full `tools/check` runs.

Every gate in a run and in its replay uses `base_pack/`, a snapshot of the
pack taken when the run starts, so a later change to `designs/` (including
this run's own `--write`) cannot change a replayed decision.

## Gates, cheapest first, stop at the first failure

`format` (blocks parse, names consistent) → `cover_sync` → `cover_policy`
(AST allowlist, `closure_core/policy.py`) → `citations` → `baseline` (0 hits;
hits by the fixed-seed random testbenches reported) → `gold` (policy: no
assertions, must `$fatal`; then scores 1; baseline holes it closes recorded)
→ `near_miss` (at least one, each scores 0, line overlap with the gold
reported; or a written `near_miss_waiver`, which passes and is always
audited) → `determinism` → `value` (mutant or spec evidence; mutants run
against every gold) → `duplicate`. See
`closure_core/gates.py` for what each checks. No gate calls a model.

## Records: `runs/propose/<run_id>/`

| Path | Content |
|---|---|
| `manifest.json` | git commit and dirty flag, image, toolchain, model and sampling, retry limit, prompt hash, context pack hash, flags |
| `prompts/` | the prompt templates used (their hash is `prompt_sha`) |
| `context_pack.json` | everything the model was shown, as data |
| `base_pack/` | the design pack the run gated against |
| `responses/stage_a.json`, `responses/<cid>/<attempt>.json` | exact messages sent, sampling parameters, response text, usage |
| `candidates.json` | parsed Stage A candidates |
| `candidates/<cid>/<attempt>/` | the bundle as gated (`item.yaml`, `cover.sv`, `gold.sv`, `near_miss/`) |
| `gates/<cid>/<attempt>.json` | every gate result for that attempt |
| `set/<cid>.json` | set-stage result |
| `written.json`, `check.json` | with `--write`: final IDs, `tools/check` outcome |
| `summary.json` | below |

Only the run that produced the shipped plan is committed (`.gitignore`
excludes `runs/propose/*`; add a `!runs/propose/<run_id>/` line for it).

## Summary

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
  `tools/propose_plan --summarize <run>` recomputes the summary.

## Commands

```bash
uv pip install -e ".[propose]"          # openai client
set -a; source .env; set +a             # PRIME_API_KEY (bills the key owner)
IMAGE=docker.io/vishokjcs/closure-bench-toolchain@sha256:79661c70cb6e254e83aa326515b897219b8980448e39fe97b417bf70bf2f713c  # arm64
tools/check                                                  # in the image first: caches docs and mutants
tools/propose_plan --image "$IMAGE" --stage-a-only --tag smoke
tools/propose_plan --image "$IMAGE" --stage-a-only --full-docs --tag smoke-full
tools/propose_plan --image "$IMAGE" --write                  # the real run
tools/propose_plan --image "$IMAGE" --replay runs/propose/<run_id>
```

## Limits

- Stage B candidates are gated against the pack as it was, not against each
  other, until the set stage; a duplicate pair costs a full gate run each.
- Every accepted item is within the proposer's ability (it wrote a gold that
  passes). The proposer (`anthropic/claude-opus-5.5`) is not one of the
  evaluated models, so this caps what can become a task rather than biasing
  tasks toward an evaluated model.
- Replay reproduces decisions given the same toolchain and pinned inputs; it
  cannot reproduce the model's responses, which is why they are recorded.
