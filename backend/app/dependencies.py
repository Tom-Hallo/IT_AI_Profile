"""Forwarding proxy for backward compatibility.

Canonical implementations reside in `app.modules.role_scoring.dependencies`.
"""

from app.modules.role_scoring.dependencies import (
    get_role_scoring_engine,
    get_role_scoring_service,
    get_scoped_role_scoring_service,
    get_skill_snapshot_source,
)

__all__ = [
    "get_role_scoring_engine",
    "get_role_scoring_service",
    "get_scoped_role_scoring_service",
    "get_skill_snapshot_source",
]
