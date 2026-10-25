"""closure-bench taskset: one task per coverage-plan item.

Rollout:
  agent sandbox    setup writes the agent-visible repo to /workspace; the agent
                   replies with a testbench (null harness) or writes
                   /workspace/submission/tb.sv itself (bash harness); finalize
                   makes sure that file exists and records it on the trace.
  grading sandbox  fresh container: setup, then only /workspace/submission is
                   restored; stage_verifier installs the grader bundle at /grader;
                   the grade metric runs `python3 -m closure_core.grader` there.

Correctness lives entirely in closure_core; this module only moves files and
parses the grader's JSON.
"""

from __future__ import annotations

import json
import shlex

import verifiers.v1 as vf

from closure_bench import prompt
from closure_core import load_design

WORKDIR = "/workspace"
SUBMISSION = f"{WORKDIR}/submission/tb.sv"
GRADER_ROOT = "/grader"
# Toolchain image pinned by digest (built from docker/toolchain, tag verilator-5.020).
DEFAULT_IMAGE = "docker.io/vishokjcs/closure-bench-toolchain@sha256:3678cddfbaca54b466be876f97aaa5beccdef1a71aced176bc6ba8ea293c4155"


class ClosureData(vf.TaskData):
    design: str
    targets: list[str]
    run_timeout: float = 60.0


class ClosureTask(vf.Task[ClosureData]):
    NEEDS_CONTAINER = True

    def _design(self):
        return load_design(self.data.design)

    async def setup(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        # Runs in both sandboxes. The empty submission makes an untouched task
        # score 0 instead of failing on a missing artifact.
        for path, text in prompt.visible_files(self._design()).items():
            await runtime.write(f"{WORKDIR}/{path}", text.encode())
        await runtime.write(SUBMISSION, b"")
        await runtime.run(["chown", "-R", "agent:agent", WORKDIR], {})

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        written = (await runtime.read(SUBMISSION, max_bytes=1_000_000)).decode(errors="replace")
        tb = written if written.strip() else prompt.extract_testbench(trace.last_reply)
        await runtime.write(SUBMISSION, tb.encode())
        # Artifacts are not kept in traces; keep the submission for regrading.
        trace.info["submission"] = tb

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
            "compiled": float(g["status"] not in ("compile_error", "compile_timeout")),
            "finished": float(g["status"] == "ok"),
            "target_hit": float(all(v > 0 for v in g["target_hits"].values())),
            "off_target_items_hit": float(off_target),
            "sim_seconds": float(g["compile_s"] + g["run_s"]),
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


class ClosureBenchTaskset(vf.Taskset[ClosureTask, ClosureConfig]):
    def load(self) -> list[ClosureTask]:
        design = load_design(self.config.design)
        tasks = []
        for item in design.plan:
            if not (design.pack / "gold" / f"{item.id}.sv").exists():
                continue  # no proof of reachability, not a task
            tasks.append(ClosureTask(ClosureData(
                id=f"{design.name}/{item.id}",
                name=item.id,
                system_prompt=prompt.SYSTEM_PROMPT,
                prompt=prompt.render(design, item, self.config.run_timeout),
                design=design.name,
                targets=[item.id],
                run_timeout=self.config.run_timeout,
                image=self.config.image,
                workdir=WORKDIR,
                agent_user="agent",
                network=vf.NetworkPolicyConfig(allow=[]),
                scoring=vf.ScoringConfig(mode="isolated",
                                         network=vf.NetworkPolicyConfig(allow=[])),
                artifacts=[vf.Artifact(source=f"{WORKDIR}/submission")],
                timeout=vf.TaskTimeout(setup=600, agent=600, finalize=120, scoring=600),
                resources=vf.TaskResources(cpu=2, memory=4),
            ), self.config.task))
        return tasks
