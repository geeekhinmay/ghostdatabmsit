"""Ghost Data deletion audit root package.

Also provides compatibility fallback for Python standard library `code` module
(which is imported by pdb and debugging tools).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Load standard library `code` module dynamically so standard library tools
# like pdb, traceback, or REPL tools don't break when importing `code`.
_stdlib_code_path = Path(sys.base_prefix) / "Lib" / "code.py"
_stdlib_code = None
if _stdlib_code_path.is_file():
    try:
        _spec = importlib.util.spec_from_file_location("_stdlib_code", _stdlib_code_path)
        if _spec and _spec.loader:
            _stdlib_code = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_stdlib_code)
    except Exception:
        pass


def __getattr__(name: str):
    if _stdlib_code and hasattr(_stdlib_code, name):
        return getattr(_stdlib_code, name)
    raise AttributeError(f"module 'code' has no attribute '{name}'")
