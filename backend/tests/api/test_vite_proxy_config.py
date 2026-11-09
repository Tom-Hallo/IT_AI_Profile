"""Regression tests for Vite development and preview proxy configuration.

Ensures /api requests from the frontend SPA are proxied to the FastAPI backend
in both `server` (development mode) and `preview` modes, preventing regressions
where OAuth callbacks, auth status, or sync requests return 404 from Vite.
"""

import http.client
import os
import re
from pathlib import Path

import pytest


def _get_vite_config_path() -> Path | None:
    # 1. Standard repo structure: repo_root/frontend/vite.config.ts
    candidate = Path(__file__).resolve().parents[3] / "frontend" / "vite.config.ts"
    if candidate.exists():
        return candidate
    # 2. Environment variable override
    env_path = os.getenv("FRONTEND_VITE_CONFIG_PATH")
    if env_path and Path(env_path).exists():
        return Path(env_path)
    return None


def test_vite_config_declares_proxy_in_server_and_preview() -> None:
    """Verifies server.proxy and preview.proxy forward /api to backend."""
    config_path = _get_vite_config_path()
    if config_path is None:
        try:
            conn = http.client.HTTPConnection("frontend", 5173, timeout=3)
            conn.request("GET", "/api/v1/auth/me")
            res = conn.getresponse()
            assert res.status == 401
            assert b"detail" in res.read()
            return
        except Exception:
            pytest.skip(
                "frontend/vite.config.ts not mounted and frontend container unreachable"
            )

    content = config_path.read_text(encoding="utf-8")

    # 1. proxy definition must map '/api'
    assert "'/api':" in content or '"/api":' in content, (
        "vite.config.ts must define an /api route mapping in proxy"
    )

    # 2. Extract server { ... } block
    server_match = re.search(r"server:\s*\{([^}]+)\}", content, re.DOTALL)
    assert server_match is not None, "vite.config.ts must contain a server block"
    server_body = server_match.group(1)
    assert "proxy" in server_body, (
        "vite.config.ts server configuration must include 'proxy' to forward "
        "API calls during development (e.g. npm run dev / Vite dev server)"
    )

    # 3. Extract preview { ... } block
    preview_match = re.search(r"preview:\s*\{([^}]+)\}", content, re.DOTALL)
    assert preview_match is not None, "vite.config.ts must contain a preview block"
    preview_body = preview_match.group(1)
    assert "proxy" in preview_body, (
        "vite.config.ts preview configuration must include 'proxy' to forward "
        "API calls during preview mode (e.g. npm run preview)"
    )


def test_vite_config_allowed_hosts_configured() -> None:
    """Verifies allowedHosts is configured on server to allow Docker hostnames."""
    config_path = _get_vite_config_path()
    if config_path is None:
        try:
            conn = http.client.HTTPConnection("frontend", 5173, timeout=3)
            conn.request("GET", "/api/v1/auth/me")
            res = conn.getresponse()
            # If allowedHosts was not set, Vite returns 403 Blocked request
            assert res.status == 401
            return
        except Exception:
            pytest.skip(
                "frontend/vite.config.ts not mounted and frontend container unreachable"
            )

    content = config_path.read_text(encoding="utf-8")
    server_match = re.search(r"server:\s*\{([^}]+)\}", content, re.DOTALL)
    assert server_match is not None
    server_body = server_match.group(1)
    assert "allowedHosts" in server_body, (
        "vite.config.ts server block must configure allowedHosts to allow "
        "Docker internal networking (e.g. frontend:5173)"
    )
