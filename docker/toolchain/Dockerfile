# closure-bench toolchain. Two targets from one file, so Verilator is the same
# package in both and coverage numbers are identical wherever a testbench runs:
#   task      Verilator 5.020 only: the agent and grading sandboxes (tag verilator-5.020)
#   pipeline  task + formal tools: tools/check, tools/formal, gates, proposer (tag formal)
# The task image must not carry the formal tools: in the bash harness the agent
# has a shell, and with SymbiYosys it could get a witness from a model checker.
# tests/test_images.py checks both.
#
# Contents: toolchain only, no project code. Grader code is staged into the
# sandbox at run time, so this image only changes when the toolchain does.
# Python libraries come from Ubuntu packages (pinned with the base image) so
# closure_core and tools/check run here with the system python3, no pip needed.
#
# Pinning:
#   - base image by its multi-platform digest (refresh with README.md step 1)
#   - verilator by exact Debian version; the build fails loudly if that
#     version ever disappears instead of silently picking up another one.
#   - formal tools (Yosys, SymbiYosys, Yices 2, Bitwuzla) from one dated OSS
#     CAD Suite release, checked by SHA-256 per architecture. Ubuntu 24.04 has
#     only Yosys 0.33 and neither SymbiYosys nor Yices/Bitwuzla. They live in
#     /opt/oss-cad-suite and are NOT on PATH: the suite ships its own Verilator,
#     which must never shadow 5.020. Formal measures; Verilator judges.

ARG BASE_IMAGE=ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac

# Builder: download, verify and prune the formal tools (2.3 GB -> ~440 MB).
FROM ${BASE_IMAGE} AS formal
ARG TARGETARCH
ARG OSS_CAD_SUITE_DATE=2026-10-09
ARG OSS_CAD_SUITE_SHA256_AMD64=20b7bd2d24e187aa87bbb3a0b70369a6aa352dac2048033eb2e68439a477ca0d
ARG OSS_CAD_SUITE_SHA256_ARM64=21ee83a9b64928709eb6f72a2303f139627de1a4df032d3e5cbc6beb7942bd8e
COPY prune_oss_cad_suite.sh /tmp/
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && case "${TARGETARCH}" in \
      amd64) arch=x64;   sum=${OSS_CAD_SUITE_SHA256_AMD64} ;; \
      arm64) arch=arm64; sum=${OSS_CAD_SUITE_SHA256_ARM64} ;; \
      *) echo "unsupported arch ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
 && d=$(echo ${OSS_CAD_SUITE_DATE} | tr -d -) \
 && curl -fsSL -o /tmp/oss.tgz \
      "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE_DATE}/oss-cad-suite-linux-${arch}-${d}.tgz" \
 && echo "${sum}  /tmp/oss.tgz" | sha256sum -c - \
 && tar -xzf /tmp/oss.tgz -C /opt \
 && bash /tmp/prune_oss_cad_suite.sh

FROM ${BASE_IMAGE} AS task

ARG VERILATOR_VERSION=5.020-1

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      verilator=${VERILATOR_VERSION} \
      g++ make perl python3 ca-certificates \
      python3-yaml python3-pypdf \
 && rm -rf /var/lib/apt/lists/*

# Unprivileged account for the agent (verifiers TaskData.agent_user);
# setup, finalize and grading run as root.
RUN useradd --create-home --shell /bin/bash agent \
 && mkdir -p /workspace \
 && chown agent:agent /workspace

WORKDIR /workspace

LABEL org.opencontainers.image.title="closure-bench toolchain" \
      org.opencontainers.image.description="Verilator ${VERILATOR_VERSION} on Ubuntu 24.04" \
      org.opencontainers.image.source="closure-bench/docker/toolchain"

# Last stage, so a plain build gives the pipeline image.
FROM task AS pipeline
COPY --from=formal /opt/oss-cad-suite /opt/oss-cad-suite
# Fail the build if a pruned tool cannot start.
RUN /opt/oss-cad-suite/bin/yosys -V \
 && /opt/oss-cad-suite/bin/sby --help >/dev/null \
 && /opt/oss-cad-suite/bin/yices-smt2 --version \
 && /opt/oss-cad-suite/bin/bitwuzla --version \
 && verilator --version | grep -q "^Verilator 5.020 "
LABEL org.opencontainers.image.description="Verilator 5.020 on Ubuntu 24.04; formal tools (OSS CAD Suite) in /opt/oss-cad-suite"
