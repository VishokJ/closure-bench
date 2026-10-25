# closure-bench

A small coverage-closure benchmark for agents, built as a `verifiers` environment.
The agent writes a testbench that reaches an uncovered behaviour in an
open-source UART; the grader re-runs it in a clean environment and checks
coverage.

Status: grader, validity gates and the Prime eval adapter in place for the first task (R1).

## Layout
- `third_party/verilog-uart/` pinned, unmodified design under test (see UPSTREAM.md)
- `designs/uart/` design pack: baseline testbenches, coverage plan (`plan.yaml`),
  cited documents (`sources.yaml`), one cover file per item, gold testbenches, waivers
- `closure_core/` simulation, coverage parsing, citation checks, mutants, gate logic
  (`gates.py`), AST policy checks on Verilator's parse (`policy.py`) and the grader;
  plain Python with no verifiers dependency
- `tools/check` validity suite: every plan item must pass every gate (citations,
  cover sync, cover policy, baseline 0, gold 1, near-miss 0, determinism, value, duplicate).
  Value needs evidence the item matters: its gold kills a mutant the baseline
  misses, or it cites a verified datasheet/README requirement
- `environments/closure_bench/` verifiers v1 adapter: one task per plan item; the
  agent's sandbox never contains the grader, golds or near-misses, and grading
  runs in a fresh, offline sandbox with only the submitted testbench restored
- `configs/` eval configs (`slice_r1.toml`: R1, null harness, Prime sandboxes)
- `tests/` unit tests for the gate logic and the grader bundle
- `tools/run_tb` run one testbench and write annotated coverage
- `docker/toolchain/` pinned Verilator 5.020 image used everywhere

## Usage
Requires Verilator 5.020 (or the toolchain image) and [uv](https://docs.astral.sh/uv/).

The cover policy reads Verilator's XML, whose layout is version-specific, so it
refuses any Verilator other than 5.020. On a host without it, run inside the image:

```bash
# Multi-platform index, as pinned in the eval configs. On Apple silicon, if Docker
# Desktop refuses the index digest, use the arm64 manifest:
#   sha256:79661c70cb6e254e83aa326515b897219b8980448e39fe97b417bf70bf2f713c
IMAGE=docker.io/vishokjcs/closure-bench-toolchain@sha256:3678cddfbaca54b466be876f97aaa5beccdef1a71aced176bc6ba8ea293c4155

# Run the baseline and see what it leaves uncovered
docker run --rm -v "$PWD":/repo -w /repo "$IMAGE" \
  tools/run_tb designs/uart/baseline/tb_uart_rx.sv --top tb_uart_rx --out results/baseline_rx

# Validity suite (downloads cited documents to ~/.cache/closure-bench)
docker run --rm -v "$PWD":/repo -w /repo \
  -v "$HOME/.cache/closure-bench":/root/.cache/closure-bench "$IMAGE" tools/check -j 8

# Unit tests: on the host (the fixture drift test skips without Verilator 5.020) ...
uv run --extra dev pytest tests
# ... or all of them in the image, with pytest installed into a gitignored folder
uv pip install --python-platform linux --python-version 3.12 --target .cache/pytest "pytest>=8"
docker run --rm -v "$PWD":/repo -w /repo -e PYTHONPATH=/repo/.cache/pytest "$IMAGE" \
  python3 -m pytest -q -p no:cacheprovider tests
```

### Evals on Prime
```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e . -e environments/closure_bench   # verifiers pinned in its pyproject
set -a; source .env; set +a                         # PRIME_API_KEY
vf-validate closure-bench --runtime.type prime -n 1 --only-gold   # gold scores 1
vf-eval @ configs/slice_r1.toml
```
