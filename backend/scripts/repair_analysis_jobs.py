"""Repair missing analysis job tables without changing Alembic history."""

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

from app.db.session import engine

MIGRATION_FILE = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20261109_0759_886985c725a6_add_analysis_jobs.py"
)


def main() -> None:
    spec = importlib.util.spec_from_file_location(
        "repair_original_analysis_jobs",
        MIGRATION_FILE,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load original migration")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with engine.begin() as connection:
        inspector = inspect(connection)

        jobs_exists = inspector.has_table("analysis_jobs", schema="ita")
        events_exists = inspector.has_table("analysis_job_events", schema="ita")

        if jobs_exists or events_exists:
            raise RuntimeError(
                "Analysis tables already exist or schema is partial. Repair aborted."
            )

        context = MigrationContext.configure(connection)
        operations = Operations(context)

        original_op = module.op

        try:
            module.op = operations
            module.upgrade()
        finally:
            module.op = original_op

        print("Restored analysis_jobs and analysis_job_events")


if __name__ == "__main__":
    main()
