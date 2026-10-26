## Difficulty mechanism (this run)

In this run you write only targets; a formal tool finds the stimulus. Each
task must make the target hard for engineering reasons: it combines at least
two distinct mechanisms, listed as `mechanism: [a, b]` in its entry, from:

- `boundary`: the exact edge of a condition (one cycle, one count, one bit);
  the item will need a twin cover for the off-by-one side.
- `sequence`: several steps in order, tracked by a register in the cover.
- `interaction`: two or more design signals in a specific combination.
- `data`: a specific multi-bit value (e.g. 8'h55) that a mistimed run cannot
  produce by accident.
- `reset_timing`: a condition timed against reset. At most two targets
  listing it are accepted per run; prefer the others.

## How many (this run)

List exactly {n} distinct task targets; in this run that replaces "prefer
fewer" above. Spread them over the design: some bind to `uart_rx` and some to
`uart_tx`, and no pair of mechanisms (say `sequence` and `data`) appears
together in more than 4 targets. If you cannot find {n} that are distinct and
well sourced, list fewer rather than near-duplicates. Waiver proposals do not
count toward {n}.
