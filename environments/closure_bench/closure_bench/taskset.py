"""closure-bench taskset: one task per coverage-plan item.

Rollout:
  agent sandbox    setup writes the agent-visible repo to /workspace; the agent
                   replies with a testbench (null harness) or writes
                   /workspace/submission/tb.sv itself (bash harness, which also
                   gets /workspace/run.sh: the grader on a testbench of its
                   choice); finalize makes sure that file exists and records it
                   on the trace.
  grading sandbox  fresh container: setup, then only /workspace/submission is
                   restored; stage_verifier installs the grader bundle at /grader;
                   the grade metric runs `python3 -m closure_core.grader` there.

Correctness lives entirely in closure_core; this module only moves files and
parses the grader's JSON.
"""

from __future__ import annotations

import json
import shlex
from typing import Literal

import verifiers.v1 as vf

from closure_bench import prompt
from closure_core import load_design

WORKDIR = prompt.WORKDIR
SUBMISSION = prompt.SUBMISSION
GRADER_ROOT = "/grader"
MAX_TB_BYTES = 1_000_000
# Toolchain image pinned by digest (built from docker/toolchain, tag verilator-5.020).
DEFAULT_IMAGE = "docker.io/vishokjcs/closure-bench-toolchain@sha256:3678cddfbaca54b466be876f97aaa5beccdef1a71aced176bc6ba8ea293c4155"
# Agent wall clock per harness. bash: room for a few dozen ~9 s simulations
# plus model time; null is a single reply.
DEFAULT_AGENT_TIMEOUT = {"null": 600.0, "bash": 1200.0}

Harness = Literal["null", "bash"]


class ClosureData(vf.TaskData):
    design: str
    targets: list[str]
    run_timeout: float = 60.0
    harness: Harness = "null"   # which prompt and workspace; must match the agent's harness
    max_turns: int | None = None  # bash: stated in the prompt; must match the agent's max_turns


class ClosureTask(vf.Task[ClosureData]):
    NEEDS_CONTAINER = True

    def _design(self):
        return load_design(self.data.design)

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        # Runs in both sandboxes. The empty submission makes an untouched task
        # score 0 instead of failing on a missing artifact.
        h = trace.agent.config.harness  # None under vf-validate: no agent runs
        if h is not None and (h.id == "null") != (self.data.harness == "null"):
            raise vf.TaskError(f"taskset harness is {self.data.harness!r} but the agent "
                               f"runs harness {h.id!r}; set both to match")
        if (h is not None and self.data.harness == "bash"
                and trace.agent.config.max_turns != self.data.max_turns):
            raise vf.TaskError(f"taskset max_turns is {self.data.max_turns!r} but the agent's "
                               f"is {trace.agent.config.max_turns!r}; the prompt states the "
                               "taskset value, so set both to match")
        design = self._design()
        for path, text in prompt.visible_files(design).items():
            await runtime.write(f"{WORKDIR}/{path}", text.encode())
        if self.data.harness == "bash":
            tools = prompt.workspace_tools(design, self.data.targets, self.data.run_timeout)
            for path, data in tools.items():
                await runtime.write(f"{WORKDIR}/{path}", data)
            await runtime.run(["chmod", "+x", f"{WORKDIR}/{prompt.RUN_SH}"], {})
        await runtime.write(SUBMISSION, b"")
        await runtime.run(["chown", "-R", "agent:agent", WORKDIR], {})

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        # A shell agent may delete the file or make it huge: either counts as
        # not written instead of failing the rollout.
        fits = await runtime.run(["sh", "-c", f'[ -f {SUBMISSION} ] && '
                                  f'[ "$(stat -L -c %s {SUBMISSION})" -le {MAX_TB_BYTES} ]'], {})
        written = ((await runtime.read(SUBMISSION, max_bytes=MAX_TB_BYTES)).decode(errors="replace")
                   if fits.exit_code == 0 else "")
        if written.strip():
            tb, source = written, "file"
        else:
            tb = prompt.extract_testbench(trace.last_reply)
            source = "reply" if tb else "none"
        # With a shell the agent owns submission/: replace it with one regular
        # file so only tb.sv (no symlinks or extra files) reaches the grader.
        await runtime.run(["rm", "-rf", f"{WORKDIR}/submission"], {})
        await runtime.write(SUBMISSION, tb.encode())
        # Artifacts are not kept in traces; keep the submission for regrading.
        trace.info["submission"] = tb
        trace.info["submission_source"] = source

    async def stage_verifier(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        for rel, data in prompt.grader_bundle(self._design()).items():
            await runtime.write(f"{GRADER_ROOT}/{rel}", data)

    @vf.metric
    async def grade(self, trace: vf.Trace, runtime: vf.Runtime) -> dict[str, float]:
        """Run the grader once; the reward reads its result from trace.info."""
        targets = " ".join(f"--target {shlex.quote(t)}" for t in self.data.targets)
        cmd = (f"cd {GRADER_ROOT} && python3 -m closure_core.grader --design "
               f"{shlex.quote(self.data.design)} {targets} "
               f"--run-timeout {self.data.run_timeout} {SUBMISSION}")
        res = await runtime.run(["sh", "-c", cmd], {})
        if res.exit_code != 0:
            # Grading itself failed: an infrastructure error, not a wrong answer.
            raise RuntimeError(f"grader failed ({res.exit_code}): {res.stderr[-2000:]}")
        g = json.loads(res.stdout)
        trace.info["grade"] = g
        off_target = sum(1 for k, v in g["plan_hits"].items() if v > 0 and k not in g["targets"])
        return {
            # A policy violation is rejected before it is built, so it never compiled.
            "compiled": float(g["status"] not in ("compile_error", "compile_timeout", "policy_violation")),
            # How often a model reaches for force, bind, hierarchical writes, ... (red-team).
            "policy_violation": float(g["status"] == "policy_violation"),
            "finished": float(g["status"] == "ok"),
            "target_hit": float(all(v > 0 for v in g["target_hits"].values())),
            "off_target_items_hit": float(off_target),
            "sim_seconds": float(g["compile_s"] + g["run_s"]),
        }

    @vf.metric
    async def budget(self, trace: vf.Trace) -> dict[str, float]:
        """Cost per rollout: model turns and provider-reported tokens over every call.

        prompt_tokens is summed per call, so the context re-sent each turn counts
        every time (that is what is billed); cache reads are reported separately.
        """
        u = trace.usage
        return {
            "turns": float(trace.num_turns),
            "turn_cap_hit": float(trace.stop_condition == "max_turns"),
            "prompt_tokens": float(u.prompt_tokens if u else 0),
            "cached_input_tokens": float((u.cached_input_tokens or 0) if u else 0),
            "output_tokens": float(u.completion_tokens if u else 0),
        }

    @vf.reward(weight=1.0)
    async def target_reached(self, trace: vf.Trace) -> float:
        return float(trace.info["grade"]["reward"])

    async def validate(self, trace: vf.Trace, runtime: vf.Runtime) -> bool:
        """Gold check through the full isolated grading path."""
        design = self._design()
        gold = (design.pack / "gold" / f"{self.data.targets[0]}.sv").read_text()
        await runtime.write(SUBMISSION, gold.encode())
        trace.info["submission"] = gold
        # grade_submission restores trace.state.artifacts; a rollout collects them
        # after finalize, so the gold check must do it itself.
        trace.state.artifacts = await vf.collect(
            runtime, self.data.artifacts, max_bytes=self.data.artifact_max_bytes)
        await vf.grade_submission(self, trace, runtime)
        return trace.reward == 1.0


class ClosureConfig(vf.TasksetConfig):
    design: str = "uart"
    image: str = DEFAULT_IMAGE
    run_timeout: float = 60.0
    harness: Harness = "null"
    """Prompt and workspace mode; set it to the agent's harness id (null | bash)."""
    agent_timeout: float | None = None
    """Agent wall clock in seconds; None takes DEFAULT_AGENT_TIMEOUT[harness]."""
    max_turns: int | None = None
    """bash: the turn cap stated in the prompt; set it to agent.max_turns (checked at setup)."""


class ClosureBenchTaskset(vf.Taskset[ClosureTask, ClosureConfig]):
    def load(self) -> list[ClosureTask]:
        design = load_design(self.config.design)
        harness = self.config.harness
        agent_timeout = self.config.agent_timeout or DEFAULT_AGENT_TIMEOUT[harness]
        tasks = []
        for item in design.plan:
            if not (design.pack / "gold" / f"{item.id}.sv").exists():
                continue  # no proof of reachability, not a task
            tasks.append(ClosureTask(ClosureData(
                id=f"{design.name}/{item.id}",
                name=item.id,
                system_prompt=prompt.system_prompt(harness),
                prompt=prompt.render(design, item, self.config.run_timeout, harness,
                                     agent_timeout if harness == "bash" else None,
                                     self.config.max_turns if harness == "bash" else None),
                design=design.name,
                targets=[item.id],
                run_timeout=self.config.run_timeout,
                harness=harness,
                max_turns=self.config.max_turns,
                image=self.config.image,
                workdir=WORKDIR,
                agent_user="agent",
                network=vf.NetworkPolicyConfig(allow=[]),
                scoring=vf.ScoringConfig(mode="isolated",
                                         network=vf.NetworkPolicyConfig(allow=[])),
                artifacts=[vf.Artifact(source=f"{WORKDIR}/submission")],
                timeout=vf.TaskTimeout(setup=600, agent=agent_timeout, finalize=120, scoring=600),
                resources=vf.TaskResources(cpu=2, memory=4),
            ), self.config.task))
        return tasks
