from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "database_url": "postgresql+psycopg://u:p@127.0.0.1:5432/d",
        "redis_url": "redis://127.0.0.1:6379/0",
    }
    values.update(overrides)
    return Settings(**values)


def test_docs_available_in_development():
    client = TestClient(create_app(_settings(app_env="development")))
    assert client.get("/api/v1/docs").status_code == 200
    assert client.get("/api/v1/openapi.json").status_code == 200


def test_docs_disabled_outside_development():
    for env in ("production", "test"):
        client = TestClient(create_app(_settings(app_env=env)))
        assert client.get("/api/v1/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404


def test_cors_allows_configured_origin():
    client = TestClient(create_app(_settings(cors_origins="http://localhost:5173")))
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_cors_rejects_other_origin():
    client = TestClient(create_app(_settings(cors_origins="http://localhost:5173")))
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in response.headers
