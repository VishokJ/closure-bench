# Authoring rules

A plan item is one behaviour of the design that the existing regression
(the baseline testbenches) never exercises. Each item becomes a task: an agent
gets the repository, this item's coverage report entry and its one-line
description, and must write a testbench that reaches it. Every item you
propose is checked mechanically; anything that breaks a rule below is
rejected with the reason.

## The bundle

- **Plan entry.** One-line `description` an engineer could act on (what must
  happen, not how to make it happen), a predicted `tier` (T0 easy, T1 medium,
  T2 hard: cycle-exact or narrow window, T3 multi-step), and `sources`.
  The description restates the cover condition in one or two plain sentences
  and names every signal and value the cover checks. It claims nothing the
  cover doesn't check: stimulus details (which word was pending first, the
  prescale you used) belong in the gold, not the description. Every design
  signal name and every sized or hex constant (8'h3C, 0x3C) in the description
  must be read by the cover; this is checked.
- **Cover file.** One module `cov_ITEM` with one cover property labelled
  `ITEM_<short_name>`, and exactly one `bind <design module> cov_ITEM u_cov_ITEM (.*);`.
  Write the literal token `ITEM`; the tool assigns the real ID.
- **Gold testbench.** Top module `tb`. It reaches the behaviour with legitimate
  stimulus through the design's ports only, and checks it.
- **Near-miss testbenches**: at least one per item. Each exercises nearly the
  same path as the gold but misses the cover by the smallest possible margin
  (one cycle early or late, the other value of the deciding bit, one step
  short of the sequence), checks with `$fatal` that it really exercised that
  path, and runs to `$finish` cleanly. Only if no near-miss is meaningful, add
  `near_miss_waiver: <the reason>` to the plan entry instead; every such item
  is reviewed by a person.

## Cover modules: observe only

Covers run inside every future grading run, so they may only observe.

- Allowed: input ports (named like the design's signals, so `.*` connects
  them; internal registers such as `bit_cnt` or `prescale_reg` can be ports
  too), `parameter`/`localparam`, local registers written with non-blocking
  assignments in `always @(posedge clk)` blocks using only `if`/`case`/`begin`,
  `cover property`, and `$past`, `$rose`, `$fell`, `$stable`.
- Not allowed: initial blocks or variable initializers (reset tracking state
  on `rst` instead; simulation starts every variable at 0), blocking or
  continuous assignments, combinational always blocks, loops, any other
  system task or function, hierarchical references, assertions, instances,
  output ports.
- Verilator 5.020 does not support `##` sequences. For multi-step behaviour,
  track progress in local registers and cover the final state.
- Make the cover exact. A cover that is true too easily (e.g. `a |-> b`,
  which holds whenever `a` is low) is hit by the baseline and rejected.
  Where correctness of data matters, require a specific value (e.g. 8'h55)
  so a mistimed run cannot satisfy it by accident.

## Gold testbenches: check, do not only reach

- Check the behaviour's observable outputs and call `$fatal` if they are
  wrong. Write checks as `if (!ok) $fatal(1, "...")`, never `assert`/`assume`:
  the grader compiles without `--assert`, so assertions never fire.
- No `force`/`release`, no hierarchical writes into the design, no `$system`,
  `$c` or file I/O.
- End with `$finish`. A run that times out, ends without `$finish`, or calls
  `$fatal`/`$stop` scores 0.
- Instantiate the design with its default parameters (overrides are rejected);
  covers may rely on the defaults, e.g. DATA_WIDTH = 8.
- Verilator runs `<=` inside initial blocks and tasks as blocking. Drive and
  sample on the falling clock edge to avoid races with the design.

## Sources

Every item cites at least one source; each is verified mechanically.

- `RTL` / `README`: `file` (repository path), `lines: [first, last]`, and an
  `anchor` string that appears verbatim on those lines.
- `DOC`: `doc` (id), `page`, `anchor` copied verbatim from the page text given
  below. The text was extracted from the PDF and has artefacts (e.g.
  `TV ALID`); copy them exactly. Use only the pages given.
- `BASE`: `point: {kind, file, line, name}`, a baseline coverage hole from the
  list below (0 hits).
- Mark a `DOC` or `README` source `role: requirement` only if it states what
  the design must do. `RTL` describes what the design does, so it is never a
  requirement.

## What makes a good item

- The baseline never exercises it, and it matters: either a bug in the
  design would make the gold fail, or a cited document requires it.
- It is distinct from every existing item and from your other candidates:
  some testbench must be able to hit one and not the other.
- Difficulty comes from the engineering (exact timing, narrow windows, deep
  sequences, combinations), never from vague wording.
