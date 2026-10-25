"""closure_core: simulation, coverage and grading for closure-bench.

Plain Python with no verifiers dependency, so everything that decides a
reward can be tested, re-run and red-teamed without a model or a sandbox.
"""

# grade() lives in closure_core.grader and is not re-exported: importing it here
# would make `python -m closure_core.grader` load the module twice (runpy warns).
from closure_core.design import Design, PlanItem, load_design

__all__ = ["Design", "PlanItem", "load_design"]
