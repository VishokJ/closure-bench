You are a verification engineer extending the coverage plan of the design
below. The repository, the baseline regression and its coverage holes, the
existing plan items and the cited documents follow.

{context}

## Your task

Write the complete bundle for this candidate:

```yaml
{candidate}
```

Follow the authoring rules above exactly. Use the literal token ITEM wherever
the item ID goes (module cov_ITEM, instance u_cov_ITEM, label ITEM_<name>).
Write `description` as a folded block scalar (`>-`, then the text indented on
the following lines), as below, so colons and quotes in it need no escaping.

Answer with these blocks and nothing else, one near_miss block per near-miss
testbench (at least one, unless the plan has a near_miss_waiver):

<plan>
description: >-
  what must happen, in one or two sentences
tier: T1
cover: ITEM_<name>
sources:
  - {type: README, role: requirement, file: ..., lines: [a, b], anchor: "..."}
</plan>
<cover>
...SystemVerilog...
</cover>
<gold>
...SystemVerilog...
</gold>
<near_miss name="short_name">
...SystemVerilog...
</near_miss>
