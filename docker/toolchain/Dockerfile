# closure-bench toolchain: the one simulator environment used everywhere
# (agent sandbox, grader sandbox, local checks), so coverage numbers are
# identical wherever a testbench runs.
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

ARG BASE_IMAGE=ubuntu:24.04@sha256:68ee22004a9109b44973313b02ff7b1de250f1de0f5ecb628d73f579aaff33ac
FROM ${BASE_IMAGE}

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
