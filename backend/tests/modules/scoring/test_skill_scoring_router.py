from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.db.session import get_session
from app.main import create_app


def test_scores_route_checks_repository_membership_and_private_consent(monkeypatch):
    user = SimpleNamespace(id=1)
    repo = SimpleNamespace(id=7, private=False)
    db = MagicMock()
    db.scalar.return_value = repo
    db.scalars.return_value.all.return_value = []
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = lambda: db
    endpoint = "/api/v1/scoring/repositories/7/skills"

    with TestClient(app) as client:
        assert client.get(endpoint).json() == []
        assert "user_repository" in str(db.scalar.call_args.args[0])
        db.scalar.return_value = None
        assert client.get(endpoint).status_code == 404
        repo.private = True
        db.scalar.side_effect = [repo, repo, None]
        monkeypatch.setattr(
            "app.modules.analysis.service.has_private_access", lambda *_: True
        )
        assert client.get(endpoint).status_code == 403


def test_report_without_verified_metrics_has_insufficient_scores():
    db = MagicMock()
    db.scalar.side_effect = [
        SimpleNamespace(id=7, private=False),
        SimpleNamespace(
            id=23, commit_sha="a" * 40, languages=[{"name": "Python"}], frameworks=[]
        ),
    ]
    db.scalars.return_value.all.return_value = []
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_session] = lambda: db

    with TestClient(app) as client:
        res = client.get("/api/v1/scoring/repositories/7/skills?report_id=23")
    assert res.status_code == 200
    [item] = res.json()
    assert item["technology"] == "Python"
    assert item["status"] == "Insufficient"
    assert item["score"] is None
    assert item["report_id"] == 23


def test_report_score_fallback_supports_offset():
    db = MagicMock()
    db.scalar.side_effect = [
        SimpleNamespace(id=7, private=False),
        SimpleNamespace(
            id=23,
            commit_sha="a" * 40,
            languages=[{"name": "Python"}, {"name": "Go"}],
            frameworks=[],
        ),
    ]
    db.scalars.return_value.all.return_value = []
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    app.dependency_overrides[get_session] = lambda: db
    with TestClient(app) as client:
        res = client.get(
            "/api/v1/scoring/repositories/7/skills?report_id=23&offset=1&limit=1"
        )
    assert res.status_code == 200
    assert [item["technology"] for item in res.json()] == ["Go"]
