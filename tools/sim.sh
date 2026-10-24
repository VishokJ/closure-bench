#!/usr/bin/env bash
# Compile a testbench against the vendored RTL with Verilator coverage on,
# run it, and write coverage.dat plus an annotated source report.
#
# Interim script; replaced by closure_core/sim.py.
# Usage: tools/sim.sh <top_module> <out_dir> <tb.sv> [extra .sv files...]
#   e.g. tools/sim.sh tb_uart_rx results/baseline_rx designs/uart/baseline/tb_uart_rx.sv
#
# Output in <out_dir>:
#   sim.log        compile + run log
#   coverage.dat   raw Verilator coverage database
#   annotated/     RTL annotated with hit counts (verilator_coverage)
set -euo pipefail

TOP="$1"; OUT="$2"; shift 2
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RTL=("$ROOT"/third_party/verilog-uart/rtl/uart.v
     "$ROOT"/third_party/verilog-uart/rtl/uart_rx.v
     "$ROOT"/third_party/verilog-uart/rtl/uart_tx.v)

mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
BUILD="$OUT/build"
rm -rf "$BUILD" "$OUT/annotated" "$OUT/coverage.dat"

{
  verilator --cc --exe --build --timing --prefix Vtop \
    --coverage-line --coverage-toggle --coverage-user \
    -Wno-fatal \
    --top-module "$TOP" --Mdir "$BUILD" -o sim \
    "$ROOT/closure_core/sim_main.cpp" "${RTL[@]}" "$@"
  COVERAGE_FILE="$OUT/coverage.dat" "$BUILD/sim"
} > "$OUT/sim.log" 2>&1 || { tail -20 "$OUT/sim.log"; echo "FAILED: see $OUT/sim.log"; exit 1; }

verilator_coverage --annotate "$OUT/annotated" --annotate-min 1 "$OUT/coverage.dat" >> "$OUT/sim.log" 2>&1
grep -E "^PASS|Total coverage" "$OUT/sim.log" || true
