"""
Verification module for generating verification checks.

Owned by: Member 4 (Hrushikesh)
"""

from code.models.schemas import AuditStep
from code.verification.verifier import _build_verification_steps_internal, build_verification_steps

# Alias for compatibility if Step is referenced
Step = AuditStep

__all__ = [
    "build_verification_steps",
    "_build_verification_steps_internal",
    "Step",
    "AuditStep",
]
