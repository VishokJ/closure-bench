# Toolchain image

Verilator 5.020 on Ubuntu 24.04, built as two targets from one Dockerfile:

- `task` (tag `verilator-5.020`): Verilator only. The agent and grader
  sandboxes. It must not carry formal tools: a bash-harness agent could run a
  model checker and get a witness.
- `pipeline` (tag `formal`, the default target): `task` plus Yosys,
  SymbiYosys, Yices 2 and Bitwuzla from a dated OSS CAD Suite release
  (SHA-256 checked) in `/opt/oss-cad-suite`, off PATH. tools/check,
  tools/formal, tools/gate_candidate and the proposer run here.

## 1. Pin the base image (done; repeat only to move to a newer base)

```bash
docker pull --platform linux/amd64 ubuntu:24.04
docker inspect --format '{{index .RepoDigests 0}}' ubuntu:24.04
```

Put the printed `ubuntu@sha256:...` digest into `BASE_IMAGE` in the Dockerfile.

## 2. Build and push

Prime sandboxes run on linux/amd64, so the image must include that platform
even when built on an Apple Silicon Mac. Build both platforms:

```bash
REPO=docker.io/<dockerhub-user>/closure-bench-toolchain
docker buildx build --platform linux/amd64,linux/arm64 --target task \
  -t "$REPO:verilator-5.020" --push docker/toolchain
docker buildx build --platform linux/amd64,linux/arm64 --target pipeline \
  -t "$REPO:formal" --push docker/toolchain
docker buildx imagetools inspect "$REPO:formal"   # index and per-platform digests to pin
```

Pin the task digest in `taskset.py` (`DEFAULT_IMAGE`) and `configs/*.toml`, the
pipeline digest in `closure_core/propose.py` (`IMAGE`).

The image must be public so Prime can pull it. The first sandbox that uses a
new image takes ~10 minutes while Prime builds its VM image; later ones start
in seconds.

## 3. Check it reproduces the reference numbers

From the repo root:

```bash
IMAGE="$REPO:verilator-5.020"
docker run --rm --platform linux/amd64 -v "$PWD":/repo -w /repo "$IMAGE" \
  bash -c 'verilator --version && tools/run_tb designs/uart/baseline/tb_uart_rx.sv --top tb_uart_rx --out /tmp/out'
```

Expected (among other lines):

```
Verilator 5.020 2024-01-01 rev (Debian 5.020-1)
PASS tb_uart_rx: 514 bytes sent, 514 received
RTL v_branch  9/12
RTL v_line    15/15
RTL v_toggle  45/76
```

## 4. Run the validity suite locally

```bash
docker run --rm --platform linux/amd64 -v "$PWD":/repo -w /repo \
  -v "$HOME/.cache/closure-bench":/root/.cache/closure-bench "$REPO:formal" tools/check
```

The cache mount keeps downloaded documents between runs.
