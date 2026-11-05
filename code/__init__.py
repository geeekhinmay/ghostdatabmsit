"""Ghost Data Still Exists — deletion-audit system.

Top-level package for the HackerRank Orchestrate October 2026 challenge.
Provides compatibility fallback for Python standard library `code` module
(which is imported by pdb and debugging tools).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

# Load standard library `code` module dynamically so standard library tools
# like pdb, traceback, or REPL tools don't break when importing `code`.
_stdlib_candidates = [
    Path(os.__file__).parent / "code.py",
    Path(sys.base_prefix) / "Lib" / "code.py",
    Path(sys.base_prefix) / f"lib/python{sys.version_info.major}.{sys.version_info.minor}" / "code.py",
    Path(sys.prefix) / f"lib/python{sys.version_info.major}.{sys.version_info.minor}" / "code.py",
    Path(sys.base_prefix) / "lib" / "code.py",
]

_stdlib_code = None
for _cand in _stdlib_candidates:
    if _cand.is_file():
        try:
            _spec = importlib.util.spec_from_file_location("_stdlib_code", _cand)
            if _spec and _spec.loader:
                _stdlib_code = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_stdlib_code)
                break
        except Exception:
            pass


def __getattr__(name: str):
    if _stdlib_code and hasattr(_stdlib_code, name):
        return getattr(_stdlib_code, name)
    raise AttributeError(f"module 'code' has no attribute '{name}'")
