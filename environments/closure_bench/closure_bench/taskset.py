"""closure-bench taskset: one task per coverage-plan item, per multi-target task, or
one campaign per module.

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

A campaign task targets every item of one design module that has a gold. The
agent submits up to max_files (default: one per target) files submission/tb_*.sv; the grade
metric runs campaign.py, which grades each file with the same grader CLI and
scores the fraction of targets hit by at least one file whose run is ok.

Correctness lives entirely in closure_core (campaign.py only takes a union of
its per-file results); this module only moves files and parses JSON.
"""

from __future__ import annotations

import json
import shlex
from typing import Literal

import verifiers.v1 as vf

from closure_bench import prompt
from closure_core import load_design

campaign = prompt.campaign

WORKDIR = prompt.WORKDIR
SUBMISSION = prompt.SUBMISSION
GRADER_ROOT = "/grader"
MAX_TB_BYTES = 1_000_000
# Toolchain image pinned by digest (built from docker/toolchain, tag verilator-5.020).
# Verilator only, on purpose: the pipeline image (closure_core.propose.IMAGE) adds formal
# tools, which an agent must not have (tests/test_images.py).
DEFAULT_IMAGE = "docker.io/vishokjcs/closure-bench-toolchain@sha256:3678cddfbaca54b466be876f97aaa5beccdef1a71aced176bc6ba8ea293c4155"
# Agent wall clock per harness. bash: room for a few dozen ~9 s simulations
# plus model time; null is a single reply.
DEFAULT_AGENT_TIMEOUT = {"null": 600.0, "bash": 1200.0}
# Campaign: up to 11 targets instead of 1; bash time scales with the simulations
# the agent runs, null only with the longer reply.
DEFAULT_CAMPAIGN_AGENT_TIMEOUT = {"null": 900.0, "bash": 3600.0}
COMPILE_TIMEOUT = 120.0  # closure_core.grader's default; sizes the campaign scoring timeout

Harness = Literal["null", "bash"]


class ClosureData(vf.TaskData):
    design: str
    targets: list[str]
    run_timeout: float = 60.0
    harness: Harness = "null"   # which prompt and workspace; must match the agent's harness
    max_turns: int | None = None  # bash: stated in the prompt; must match the agent's max_turns
    campaign: str | None = None   # design module of a campaign task; None: all-or-nothing task
    max_files: int | None = None  # campaign: files graded (non-empty, first by name)


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
            tools = prompt.workspace_tools(design, self.data.targets, self.data.run_timeout,
                                           max_files=self.data.max_files)
            for path, data in tools.items():
                await runtime.write(f"{WORKDIR}/{path}", data)
            await runtime.run(["chmod", "+x", f"{WORKDIR}/{prompt.RUN_SH}"], {})
        if self.data.campaign is not None:
            await runtime.run(["mkdir", "-p", prompt.SUBMISSION_DIR], {})
        else:
            await runtime.write(SUBMISSION, b"")
        await runtime.run(["chown", "-R", "agent:agent", WORKDIR], {})

    async def finalize(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        if self.data.campaign is not None:
            return await self._finalize_campaign(trace, runtime)
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

    async def _finalize_campaign(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        # Only regular files (find -type f: no symlinks) named tb_*.sv, at most
        # MAX_FILE_BYTES each (campaign.eligible); of those, the first max_files
        # non-blank ones by name (campaign.keep), so empty files take no slot.
        # NUL-separated so no file name can forge a record.
        ls = await runtime.run(["find", prompt.SUBMISSION_DIR, "-maxdepth", "1", "-type", "f",
                                "-printf", "%s %f\\0"], {})
        sizes = {}
        for rec in (ls.stdout if ls.exit_code == 0 else "").split("\0"):
            if rec:
                size, _, name = rec.partition(" ")
                sizes[name] = int(size)
        files = {}
        for name in campaign.eligible(sizes):
            if len(files) == self.data.max_files:
                break
            text = (await runtime.read(f"{prompt.SUBMISSION_DIR}/{name}",
                                       max_bytes=campaign.MAX_FILE_BYTES)).decode(errors="replace")
            files |= campaign.keep({name: text}, 1)
        source = "file" if files else "reply"
        if not files:
            files = prompt.extract_testbenches(trace.last_reply, self.data.max_files)
            source = "reply" if files else "none"
        await self._write_submission(runtime, files)
        trace.info["submission"] = files  # name -> text; artifacts are not kept in traces
        trace.info["submission_source"] = source

    async def _write_submission(self, runtime: vf.Runtime, files: dict[str, str]) -> None:
        # submission/ then holds exactly these regular files and nothing else.
        await runtime.run(["rm", "-rf", prompt.SUBMISSION_DIR], {})
        await runtime.run(["mkdir", "-p", prompt.SUBMISSION_DIR], {})
        for name, text in files.items():
            await runtime.write(f"{prompt.SUBMISSION_DIR}/{name}", text.encode())

    async def stage_verifier(self, trace: vf.Trace, runtime: vf.Runtime) -> None:
        for rel, data in prompt.grader_bundle(self._design()).items():
            await runtime.write(f"{GRADER_ROOT}/{rel}", data)

    @vf.metric
    async def grade(self, trace: vf.Trace, runtime: vf.Runtime) -> dict[str, float]:
        """Run the grader once; the reward reads its result from trace.info."""
        if self.data.campaign is not None:
            return await self._grade_campaign(trace, runtime)
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

    def _campaign_cmd(self, files: str) -> str:
        targets = " ".join(f"--target {shlex.quote(t)}" for t in self.data.targets)
        return (f"cd {GRADER_ROOT} && python3 campaign.py --design {shlex.quote(self.data.design)} "
                f"{targets} --run-timeout {self.data.run_timeout} "
                f"--max-files {self.data.max_files} {files}")

    async def _grade_campaign(self, trace: vf.Trace, runtime: vf.Runtime) -> dict[str, float]:
        res = await runtime.run(["sh", "-c", self._campaign_cmd(f"--dir {prompt.SUBMISSION_DIR}")], {})
        if res.exit_code != 0:
            raise RuntimeError(f"campaign grader failed ({res.exit_code}): {res.stderr[-2000:]}")
        c = json.loads(res.stdout)
        trace.info["grade"] = c  # per-file statuses, hits and diagnostics under "files"
        statuses = [g["status"] for g in c["files"].values()]
        return {
            "targets_hit": float(c["targets_hit"]),
            "targets": float(len(c["targets"])),
            "files": float(len(statuses)),
            # Per-file statuses as counts; a policy_violation file contributes nothing.
            **{f"files_{s}": float(statuses.count(s)) for s in campaign.STATUSES},
            "sim_seconds": float(sum(g["compile_s"] + g["run_s"] for g in c["files"].values())),
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
        """1.0 iff every target is hit (single-target task); for a campaign task
        the fraction of targets hit (trace.info["grade"]["reward_kind"] == "fraction")."""
        return float(trace.info["grade"]["reward"])

    async def validate(self, trace: vf.Trace, runtime: vf.Runtime) -> bool:
        """Gold check through the full isolated grading path."""
        if self.data.campaign is not None:
            return await self._validate_campaign(trace, runtime)
        design = self._design()
        gold = (design.pack / "gold" / f"{self.data.name}.sv").read_text()
        await runtime.write(SUBMISSION, gold.encode())
        trace.info["submission"] = gold
        # grade_submission restores trace.state.artifacts; a rollout collects them
        # after finalize, so the gold check must do it itself.
        trace.state.artifacts = await vf.collect(
            runtime, self.data.artifacts, max_bytes=self.data.artifact_max_bytes)
        await vf.grade_submission(self, trace, runtime)
        return trace.reward == 1.0

    async def _validate_campaign(self, trace: vf.Trace, runtime: vf.Runtime) -> bool:
        """Golds within the file cap must reach reward 1 through the isolated path.

        By default the cap is one file per target, so every gold is submitted.
        With a smaller max_files the golds are first graded here, one by one,
        and a greedy cover of the targets picks at most max_files of them.
        """
        design = self._design()
        golds = {f"tb_{t}.sv": design.golds[t].read_text() for t in self.data.targets}
        if len(golds) <= self.data.max_files:
            return await self._grade_golds(trace, runtime, golds)
        await self.stage_verifier(trace, runtime)
        for name, text in golds.items():
            await runtime.write(f"/tmp/golds/{name}", text.encode())
        res = await runtime.run(["sh", "-c", self._campaign_cmd(
            " ".join(f"/tmp/golds/{n}" for n in golds))], {})
        if res.exit_code != 0:
            raise RuntimeError(f"campaign grader failed ({res.exit_code}): {res.stderr[-2000:]}")
        hits = {n.removeprefix("/tmp/golds/"): {t for t, h in g["target_hits"].items() if h > 0}
                for n, g in json.loads(res.stdout)["files"].items() if g["status"] == "ok"}
        left, pick = set(self.data.targets), {}
        while left and len(pick) < self.data.max_files:
            best = max(sorted(hits), key=lambda n: len(hits[n] & left))
            if not hits[best] & left:
                break
            pick[best] = golds[best]
            left -= hits[best]
        return await self._grade_golds(trace, runtime, pick)

    async def _grade_golds(self, trace: vf.Trace, runtime: vf.Runtime, files: dict[str, str]) -> bool:
        await self._write_submission(runtime, files)
        trace.info["submission"] = files
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
    tasks: Literal["single", "multi", "campaign"] = "single"
    """single: one all-or-nothing task per plan item; multi: the multi-target tasks in the
    design's multi.yaml; campaign: one task per design module, targeting all its items with
    golds, reward = fraction of targets hit."""
    max_files: int | None = None
    """campaign: testbench files graded per task; None takes the task's number of targets."""


class ClosureBenchTaskset(vf.Taskset[ClosureTask, ClosureConfig]):
    def load(self) -> list[ClosureTask]:
        if self.config.tasks == "campaign":
            return self._load_campaigns()
        design = load_design(self.config.design)
        harness = self.config.harness
        agent_timeout = self.config.agent_timeout or DEFAULT_AGENT_TIMEOUT[harness]
        tasks = []
        specs = ({it.id: (it.id,) for it in design.plan} if self.config.tasks == "single"
                 else design.multi)
        for name, targets in specs.items():
            if not (design.pack / "gold" / f"{name}.sv").exists():
                continue  # no proof of reachability, not a task
            tasks.append(ClosureTask(ClosureData(
                id=f"{design.name}/{name}",
                name=name,
                system_prompt=prompt.system_prompt(harness),
                prompt=prompt.render(design, [design.item(t) for t in targets], self.config.run_timeout,
                                     harness, agent_timeout if harness == "bash" else None,
                                     self.config.max_turns if harness == "bash" else None, task_id=name),
                design=design.name,
                targets=list(targets),
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

    def _load_campaigns(self) -> list[ClosureTask]:
        design = load_design(self.config.design)
        harness = self.config.harness
        agent_timeout = self.config.agent_timeout or DEFAULT_CAMPAIGN_AGENT_TIMEOUT[harness]
        modules: dict[str, list] = {}
        for item in design.plan:
            if item.id in design.golds:  # no proof of reachability, not a target
                modules.setdefault(prompt.module_of(design, item), []).append(item)
        tasks = []
        for module, items in modules.items():
            max_files = self.config.max_files or len(items)
            # Files are graded one after another: worst case every file hits both limits.
            scoring = 300 + max_files * (COMPILE_TIMEOUT + self.config.run_timeout)
            tasks.append(ClosureTask(ClosureData(
                id=f"{design.name}/campaign_{module}",
                name=f"campaign_{module}",
                system_prompt=prompt.system_prompt(harness, max_files),
                prompt=prompt.render_campaign(design, module, items, self.config.run_timeout,
                                              max_files, harness,
                                              agent_timeout if harness == "bash" else None,
                                              self.config.max_turns if harness == "bash" else None),
                design=design.name,
                targets=[it.id for it in items],
                run_timeout=self.config.run_timeout,
                harness=harness,
                max_turns=self.config.max_turns,
                campaign=module,
                max_files=max_files,
                image=self.config.image,
                workdir=WORKDIR,
                agent_user="agent",
                network=vf.NetworkPolicyConfig(allow=[]),
                scoring=vf.ScoringConfig(mode="isolated",
                                         network=vf.NetworkPolicyConfig(allow=[])),
                artifacts=[vf.Artifact(source=prompt.SUBMISSION_DIR)],
                timeout=vf.TaskTimeout(setup=600, agent=agent_timeout, finalize=120, scoring=scoring),
                resources=vf.TaskResources(cpu=2, memory=4),
            ), self.config.task))
        return tasks
