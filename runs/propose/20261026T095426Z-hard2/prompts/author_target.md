You are a verification engineer extending the coverage plan of the design
below. The repository, the baseline regression and its coverage holes, the
existing plan items, the cited documents and the formal environment (the
input assumptions) follow.

{context}

## Your task

Write the target for this candidate: its plan entry, its cover and,
optionally, a twin cover. Do not write a gold or near-miss testbench. A
formal tool searches for stimulus that reaches your cover, within the input
environment above; its witness becomes the gold, and the simulator then
checks that the witness really hits the cover. A cover the tool cannot reach
is rejected, so make the condition exact but reachable.

```yaml
{candidate}
```

Follow the authoring rules above for the plan entry, the sources and the
cover module; the rules for gold and near-miss testbenches do not apply. An
item needs a near-miss, so give either:

- a **twin**: a second cover module `cov_ITEM_twin` with one cover property
  (label `ITEM_twin_<name>`) and `bind <design module> cov_ITEM_twin u_cov_ITEM_twin (.*);`, for the
  off-by-one condition next to the target (one cycle early or late, the
  other value of the deciding bit, one step short of the sequence). The twin
  must be reachable, and the formal witness for the twin must not hit the
  target; otherwise the boundary is not exact and the item is rejected. Or
- `near_miss_waiver: <the reason>` in the plan entry, if no near-miss is
  meaningful; every such item is reviewed by a person.

List the difficulty mechanisms in the plan entry (`mechanism: [a, b]`, at
least two distinct), and make the cover carry every one; each is checked:

- `boundary`: a twin cover (above) for the off-by-one side;
- `sequence`: a tracking register in the cover;
- `interaction`: the cover reads two or more design signals besides clk/rst;
- `data`: the cover compares against a multi-bit constant (e.g. 8'h55);
- `reset_timing`: a condition timed against reset (at most two targets per run).

A formal witness only reaches the behaviour and checks nothing, so it kills
no mutants: the item's value must come from a `DOC` or `README` source with
`role: requirement`.

Write `description` as a folded block scalar (`>-`, then the text indented on
the following lines), as below, so colons and quotes in it need no escaping.

Use the literal token ITEM wherever the item ID goes (module cov_ITEM,
instance u_cov_ITEM, label ITEM_<name>). Answer with these blocks and nothing
else (the twin block is optional):

<plan>
description: >-
  what must happen, in one or two sentences
tier: T1
mechanism: [boundary, data]
cover: ITEM_<name>
sources:
  - {type: README, role: requirement, file: ..., lines: [a, b], anchor: "..."}
</plan>
<cover>
...SystemVerilog...
</cover>
<twin>
...SystemVerilog...
</twin>
