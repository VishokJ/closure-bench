"""closure_core: simulation, coverage and grading for closure-bench.

Plain Python with no verifiers dependency, so everything that decides a
reward can be tested, re-run and red-teamed without a model or a sandbox.
"""

from closure_core.design import Design, PlanItem, load_design
from closure_core.grader import GradeResult, grade

__all__ = ["Design", "GradeResult", "PlanItem", "grade", "load_design"]
