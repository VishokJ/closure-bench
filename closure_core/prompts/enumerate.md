You are a verification engineer extending the coverage plan of the design
below. The repository, the baseline regression and its coverage holes, the
existing plan items and the cited documents follow.

{context}

## Your task

List candidate plan items: behaviours the baseline never exercises that a
verification engineer would want closed. Also list holes you believe should
be waived rather than closed (unreachable, illegal stimulus, not observable),
with the reason; waivers are reviewed by a person, never accepted
automatically.

Do not repeat an existing plan item. Prefer fewer, distinct, well-sourced
items over many similar ones.

Answer with one block and nothing after it:

<candidates>
- title: short name
  kind: task            # or: waiver
  target_module: uart_rx  # the design module the cover binds to
  behaviour: what must happen, in one or two sentences
  why_baseline_misses: one sentence
  sources:              # what you would cite (verified later)
    - {type: DOC, doc: pc16550d, page: 16}
    - {type: RTL, file: third_party/verilog-uart/rtl/uart_rx.v, lines: [120, 127]}
    - {type: BASE, point: {kind: v_toggle, file: uart_rx.v, line: 62, name: "prescale[4]"}}
</candidates>

Quote any value that contains brackets, colons or commas, as in `"prescale[4]"`.
