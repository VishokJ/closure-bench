You are a verification engineer extending the coverage plan of the design
below. The repository, the baseline regression and its coverage holes, the
existing plan items and the cited documents follow.

{context}

## Items accepted in the first pass of this run (do not repeat)

{accepted}

## Remaining baseline survivors

Each mutant below is a one-line change to the RTL. Every baseline testbench
and every accepted gold still passes on it, so no existing check would notice
the bug. A gold kills a mutant if it passes on the original RTL and fails
(`$fatal`, timeout, or no `$finish`) on the mutant.

{survivors}

## Your task

Address every survivor above, each exactly once:

- either propose a plan item whose gold would kill it: a behaviour the design
  must have that this mutant breaks, with a cover and a self-checking gold.
  List the survivors the item targets under `targets`; one item may target
  several survivors.
- or say in one line why no testbench can kill it: it is equivalent (cannot
  change any behaviour), or the difference is not observable at the design's
  ports. Reasons are recorded for review; they never become waivers.

Follow the authoring rules above. Do not repeat an existing plan item or an
item accepted in the first pass.

Answer with these two blocks and nothing after them:

<candidates>
- title: short name
  kind: task
  target_module: uart_rx
  behaviour: what must happen, in one or two sentences
  why_baseline_misses: one sentence
  targets: ["uart_rx.v:133:inc:0", "uart_rx.v:133:dec:0"]
  sources:
    - {type: RTL, file: third_party/verilog-uart/rtl/uart_rx.v, lines: [130, 134]}
</candidates>
<unkillable>
- {mutant: "uart_rx.v:120:inv:0", reason: "one line"}
</unkillable>
