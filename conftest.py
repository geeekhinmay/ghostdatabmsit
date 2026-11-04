"""
Pytest configuration.

Inserts the repository root into sys.path so that ``import code.xxx``
resolves to our project package rather than colliding with the stdlib
``code`` module only when running via pytest.

NOTE: The ``code/`` package name shadows the stdlib ``code`` module.
Python's pdb, which pytest imports for debugging, requires stdlib ``code``.
We solve this by:
  1. Removing the repo root from sys.path during pdb import
  2. Then ensuring our project is importable
"""
import sys
import os

# The repo root where our code/ directory lives
_repo_root = os.path.dirname(os.path.abspath(__file__))

# Ensure repo root is in sys.path for our project imports
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
