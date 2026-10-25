"""tools/check loaded as a module (it has no .py extension)."""

from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader

from closure_core.design import find_repo_root

_loader = SourceFileLoader("check", str(find_repo_root() / "tools/check"))
check = module_from_spec(spec_from_loader("check", _loader))
_loader.exec_module(check)
