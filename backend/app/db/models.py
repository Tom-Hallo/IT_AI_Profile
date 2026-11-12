"""Central registry of all SQLAlchemy models.

Importing this module ensures all ORM models are registered in Base.metadata
and Base.registry, preventing missing mapper/relationship lookup failures
at runtime (e.g., when initializing relationships between User and Assessment).
"""

from __future__ import annotations

from sqlalchemy.orm import configure_mappers

import app.modules.ai_mentor.usage_models  # noqa: F401

# Import all business models to register them on Base.registry and Base.metadata
import app.modules.analysis.finding_models
import app.modules.analysis.models
import app.modules.assessments.models
import app.modules.auth.models
import app.modules.cvs.models
import app.modules.github.models
import app.modules.github.selection_models
import app.modules.roadmaps.models
import app.modules.scoring.models
import app.modules.users.models  # noqa: F401
from app.db.base import Base


def init_models() -> None:
    """Ensure all mappers are compiled and validated."""
    configure_mappers()


# Run configure_mappers on module import to validate all relationship bindings
init_models()

__all__ = [
    "Base",
    "init_models",
]
