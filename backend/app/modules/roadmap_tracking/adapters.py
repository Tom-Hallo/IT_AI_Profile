"""Replace these adapters with PBI-023/PBI-030 services when merged.
Mock data is explicit and disabled unless PBI024_DEMO_MODE=1; never use in production.
"""

import os

from .engine import Snapshot


class SnapshotNotFound(Exception):
    pass


class MockSnapshotProvider:
    def get(self, snapshot_id: str, user_id: int) -> Snapshot:
        if os.getenv("PBI024_DEMO_MODE") != "1" or os.getenv("APP_ENV", "").lower() in {
            "production",
            "prod",
        }:
            raise SnapshotNotFound("Demo snapshot provider disabled")
        fixtures = {
            "demo-valid": Snapshot(
                "demo-valid",
                user_id,
                "public",
                "v1",
                "last-90-days",
                {
                    "Python": [
                        {"verified": True, "ref": "demo://evidence/python/commit-a1"}
                    ],
                    "FastAPI": [
                        {"verified": True, "ref": "demo://evidence/fastapi/commit-b2"}
                    ],
                },
            ),
            "demo-wrong-rubric": Snapshot(
                "demo-wrong-rubric", user_id, "public", "v2", "last-90-days", {}
            ),
            "demo-invalid": Snapshot(
                "demo-invalid", user_id, "public", "v1", "last-90-days", {}, False
            ),
        }
        if snapshot_id not in fixtures:
            raise SnapshotNotFound("Snapshot not found")
        return fixtures[snapshot_id]


snapshot_provider = MockSnapshotProvider()
