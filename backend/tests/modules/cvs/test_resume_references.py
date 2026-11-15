"""FR-026 checks for catalog rights, outcome evidence and CV isolation."""

from dataclasses import replace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db.session import get_session
from app.main import create_app
from app.modules.auth.service import create_session, revoke_session
from app.modules.cvs import references
from app.modules.cvs.models import CV
from app.modules.cvs.reference_catalog import (
    APPROVED_SOURCES,
    OutcomeEvidence,
    Reference,
)
from app.modules.cvs.references import ReferenceQuery, search_references
from tests.modules.role_scoring import conftest as role_fixtures
from tests.modules.role_scoring import test_scoped_postgres as pg_fixtures

db = pg_fixtures.db
world = role_fixtures.world
make_client = role_fixtures.make_client
PATH = "/api/v1/cvs/references"


def search(role="Backend Developer", company="Microsoft"):
    return search_references(ReferenceQuery(company=company, role=role))


@pytest.mark.parametrize(
    "role,source_id",
    [
        ("Sr. Back-End Developer", "lxlynx-markdown"),
        ("Lead,Frontend", "david-typst"),
        ("Développeur Full-Stack", "david-typst"),
        ("Kỹ sư dữ liệu", "timmy-data"),
        ("Thực tập phần mềm", "milan-junior"),
        ("SRE", "lxlynx-markdown"),
        ("Android Engineer", "jake-latex"),
    ],
)
def test_real_catalog_fallback_by_role(role, source_id):
    result = search(role)
    assert result.mode == "general"
    assert source_id in {row.id for row in result.references}
    assert "tránh sao chép" in result.disclaimer
    for row in result.references:
        source = APPROVED_SOURCES[row.id]
        assert row.source == source.publisher
        assert row.source_url == source.url
        assert row.rights_url == source.rights_url
        assert row.rights_checked_on == source.checked_on
        assert row.license in {"MIT", "CC BY 4.0"}
        assert urlsplit(row.source_url).scheme == "https"
        assert urlsplit(row.rights_url).scheme == "https"
        assert row.outcome_status == "unverified"
        assert row.outcome_stage == "unknown"
        assert row.outcome_evidence_url is None


def test_no_keywords_or_catalog_results():
    for role in ("Backendish", "Legal Counsel", "!"):
        response = search(role)
        assert response.mode == "empty"
        assert response.references == []


def test_source_outside_allowlist_is_excluded_even_with_evidence(monkeypatch):
    candidate = Reference(
        source="blocked-public-site",
        title="Should never be seen",
        roles=("backend",),
        pattern="Unlicensed copy",
        company="Microsoft",
        evidence=OutcomeEvidence(
            company="Microsoft",
            role="Backend Developer",
            stage="offer",
            publisher="Test employer",
            url="https://employer.example/outcome",
        ),
    )
    monkeypatch.setattr(references, "CATALOG", (candidate,))
    assert search().mode == "empty"


def approved_test_entry(evidence):
    return Reference(
        source="lxlynx-markdown",
        title="Test evidence boundary",
        roles=("backend",),
        pattern="Testing only",
        company="ÁCME Labs",
        evidence=evidence,
    )


def test_verified_requires_matching_company_role_and_public_evidence(monkeypatch):
    evidence = OutcomeEvidence(
        company="Acme Labs",
        role="Backend Developer",
        stage="interview",
        publisher="Test employer",
        url="https://employer.example/outcome",
    )
    general = references.CATALOG[0]
    monkeypatch.setattr(references, "CATALOG", (general, approved_test_entry(evidence)))
    response = search(company="ACME LABS", role="backend developer")
    assert response.mode == "verified"
    assert len(response.references) == 1
    row = response.references[0]
    assert row.outcome_stage == "interview"
    assert row.outcome_evidence_url == evidence.url
    for company, role in (
        ("AC MELABS", "Backend Developer"),
        ("Acme Labs International", "Backend Developer"),
        ("Acme Labs", "Senior Backend Developer"),
    ):
        result = search(company=company, role=role)
        assert result.mode == "general"
        assert all(row.outcome_evidence_url is None for row in result.references)

    for invalid in (
        None,
        replace(evidence, company="Different employer"),
        replace(evidence, url="http://employer.example/proof"),
        replace(evidence, url="https://employer.example@unreviewed.example/proof"),
        replace(evidence, url="https://employer.example:bad/proof"),
    ):
        monkeypatch.setattr(
            references, "CATALOG", (general, approved_test_entry(invalid))
        )
        result = search(company="Acme Labs")
        assert result.mode == "general"
        assert all(row.outcome_status == "unverified" for row in result.references)


def test_authenticated_contract_and_no_cv_reads(db, world):
    owner = world.user("references-owner@example.test")
    other = world.user("references-other@example.test")
    private_marker = "Owner-only CV text"
    cv = CV(
        user_id=owner.id,
        content={"source": "user_upload", "version": 1, "text": private_marker},
    )
    db.add(cv)
    db.commit()
    cv_id = cv.id
    owner_id, other_id = owner.id, other.id
    queries = []

    def capture(_connection, _cursor, statement, *_args):
        queries.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    params = {"company": "Microsoft", "role": "Backend Developer"}
    sessions = []
    try:
        with TestClient(app) as client:
            assert client.get(PATH, params=params).status_code == 401
            for user_id in (owner_id, other_id):
                token = create_session(user_id)
                sessions.append(token)
                client.cookies.set("ita_session", token)
                response = client.get(PATH, params=params)
                assert response.status_code == 200
                assert response.headers["cache-control"] == "no-store"
                assert response.json()["mode"] == "general"
                assert private_marker not in response.text
            assert all("ita.cvs" not in sql for sql in queries)
            assert client.get(f"/api/v1/cvs/{cv_id}").status_code == 404
            client.cookies.set("ita_session", sessions[0])
            assert client.get(f"/api/v1/cvs/{cv_id}").json()["text"] == private_marker
            assert (
                client.get(
                    PATH, params={**params, "source_url": "file:///etc/passwd"}
                ).status_code
                == 422
            )
            assert (
                client.get(PATH, params={"company": " ", "role": "backend"}).status_code
                == 422
            )
            assert client.get(PATH, params={"role": "backend"}).status_code == 422
    finally:
        event.remove(engine, "before_cursor_execute", capture)
        for token in sessions:
            revoke_session(token)
