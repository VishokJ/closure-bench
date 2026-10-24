# closure-bench

A small coverage-closure benchmark for agents, built as a `verifiers` environment.
The agent writes a testbench that reaches an uncovered behaviour in an
open-source UART; the grader re-runs it in a clean environment and checks
coverage.

Status: baseline coverage flow in place.

## Layout
- `third_party/verilog-uart/` pinned, unmodified design under test (see UPSTREAM.md)
- `designs/uart/baseline/` baseline testbenches: SV port of the upstream tests
- `closure_core/sim_main.cpp` simulation driver, owned by the grader: it, not
  the testbench, decides where coverage is written and whether a run finished
- `tools/sim.sh` compile a testbench with Verilator coverage, run it, annotate

## Run the baseline
Requires Verilator 5.020.

```bash
tools/sim.sh tb_uart_rx results/baseline_rx designs/uart/baseline/tb_uart_rx.sv
tools/sim.sh tb_uart_tx results/baseline_tx designs/uart/baseline/tb_uart_tx.sv
```
