# Gold testbenches

`<ID>.sv` proves plan item `<ID>` reachable with legitimate stimulus (top module
`tb`, graded exactly like a submission).

Authoring rule: a gold testbench must **check** the behaviour, not only reach
it. It checks the outputs that behaviour defines and calls `$fatal` if they are
wrong (R1: frame_error must pulse). Write checks as `if (!ok) $fatal(...)`,
never `assert`/`assume`: the grader compiles without `--assert`, so assertions
never fire and a gold that relies on them can never fail. Every gold is run against the mutants that
survive the baseline, and a mutant counts as killed only when a testbench fails
on it, so a reach-only gold kills nothing.

Kills are one of two kinds of value evidence (tools/check, gate `value`); the
other is a verified requirement citation. An item with a requirement passes
without kills, but its gold must still self-check: the kill data feeds the
survivor bookkeeping and the report, and a gold that cannot fail tells us
nothing about the behaviour it reaches.
