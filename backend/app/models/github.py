"""Forwarding proxy for backward compatibility.

Canonical models reside in `app.modules.github.models`.
"""

from app.modules.github.models import Repository, user_repository

__all__ = [
    "Repository",
    "user_repository",
]
