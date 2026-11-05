"""
Terminal Logger for NORTHSTAR Frontend.

Guarantees that every user action, button click, case inspection, and audit
execution in the browser is immediately printed to the active terminal/console
window where the server was launched.
"""

from __future__ import annotations

import sys
from datetime import datetime


def log_to_terminal(action: str, details: str = "") -> None:
    """Print a prominent, formatted event banner directly to the OS terminal."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"\n{'='*75}\n[STREAMLIT USER ACTION @ {now}] {action}\n"
    if details:
        line += f"{details}\n"
    line += f"{'='*75}\n"

    # Write directly to the operating system terminal standard output
    try:
        if sys.__stdout__:
            sys.__stdout__.write(line)
            sys.__stdout__.flush()
    except Exception:
        pass

    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:
        pass
