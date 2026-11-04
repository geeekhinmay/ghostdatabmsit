import sys
import os

# Fix for Python stdlib 'code' module collision during pytest debugging
_repo_root = os.path.dirname(os.path.abspath(__file__))
if _repo_root in sys.path:
    sys.path.remove(_repo_root)

# Let pytest configure normally, then re-insert root if needed
def pytest_configure(config):
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)