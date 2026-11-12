"""Test Architecture Evidence Provider (PBI-017) — dùng guard authz/consent thật."""

from __future__ import annotations

import pytest

from app.modules.role_scoring.access import DbRepositoryAccessGuard
from app.modules.role_scoring.architecture_provider import (
    ArchitectureEvidencePolicy,
    ArchitectureStatus,
    DbArchitectureEvidenceProvider,
    RepositoryEvidenceStatus,
)
from app.modules.role_scoring.errors import (
    PrivateConsentRequiredError,
    RepositoryNotFoundError,
)
from tests.modules.role_scoring.conftest import (
    SECRET_CONTENT,
    SECRET_RATIONALE,
    SHA,
)

API = ("api_service", "backend/app/api/router.py", "source_code")
WORKERS = ("background_workers", "backend/app/workers/worker.py", "source_code")
LAYERED = ("layered_architecture", "backend/app/services/s.py", "directory_structure")


def provider(db, user, policy=None):
    guard = DbRepositoryAccessGuard(db, user)
    return DbArchitectureEvidenceProvider(db, user.id, guard, policy)


def codes(result) -> set[str]:
    return {i.code for i in result.limitations}


def test_public_repo_returns_references_only(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    report = world.report(repo, [API, WORKERS])

    result = provider(db, user).get([repo.id])

    assert result.status == ArchitectureStatus.AVAILABLE
    ev = result.evidence_set
    assert ev is not None
    assert ev.report_ref == f"analysis_report:{report.id}"
    assert ev.commit_sha == SHA
    assert ev.repository_ids == [str(repo.id)]
    assert {e.classification for e in ev.evidence} == {
        "api_service",
        "background_workers",
    }
    assert all(e.verified for e in ev.evidence)
    assert all(e.rationale is None for e in ev.evidence)
    dumped = ev.model_dump_json()
    assert SECRET_CONTENT not in dumped and SECRET_RATIONALE not in dumped


def test_directory_name_evidence_is_excluded_and_reported(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [API, LAYERED])

    result = provider(db, user).get([repo.id])

    assert {e.classification for e in result.evidence_set.evidence} == {"api_service"}
    info = result.repositories[0]
    assert info.excluded_by_source == {"directory_structure": 1}
    assert "EVIDENCE_SOURCE_EXCLUDED" in codes(result)


def test_policy_can_allow_directory_structure_explicitly(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [LAYERED])
    policy = ArchitectureEvidencePolicy(excluded_evidence_sources=frozenset())

    result = provider(db, user, policy).get([repo.id])

    assert len(result.evidence_set.evidence) == 1


def test_missing_report_is_not_analyzed_not_fabricated(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)

    result = provider(db, user).get([repo.id])

    assert result.status == ArchitectureStatus.NOT_ANALYZED
    assert result.evidence_set is None
    assert result.repositories[0].status == RepositoryEvidenceStatus.NO_ANALYSIS
    assert "REPOSITORY_NOT_ANALYZED" in codes(result)


def test_report_without_matching_evidence_gives_empty_set(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [])

    result = provider(db, user).get([repo.id])

    assert result.status == ArchitectureStatus.AVAILABLE
    assert result.evidence_set is not None
    assert result.evidence_set.evidence == []


def test_unsupported_classification_and_non_architecture_rows_ignored(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [API, ("clean_hexagonal_excellence", "x.py", "source_code")])

    result = provider(db, user).get([repo.id])

    assert [e.classification for e in result.evidence_set.evidence] == ["api_service"]


def test_unverified_contribution_marks_evidence_unverified(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)  # không có RepositoryVerification
    world.report(repo, [API])

    result = provider(db, user).get([repo.id])

    assert all(not e.verified for e in result.evidence_set.evidence)
    assert "CONTRIBUTION_NOT_VERIFIED" in codes(result)
    assert result.repositories[0].contribution_verified is False


def test_non_verified_status_is_not_verified(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo, status="unknown")
    world.report(repo, [API])

    result = provider(db, user).get([repo.id])

    assert all(not e.verified for e in result.evidence_set.evidence)


def test_verification_requirement_can_be_disabled_by_policy(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.report(repo, [API])
    policy = ArchitectureEvidencePolicy(require_verified_contribution=False)

    result = provider(db, user, policy).get([repo.id])

    assert all(e.verified for e in result.evidence_set.evidence)


def test_latest_report_per_repository_is_used(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [API], commit="1" * 40)
    newest = world.report(repo, [WORKERS], commit="2" * 40)

    result = provider(db, user).get([repo.id])

    assert result.evidence_set.commit_sha == "2" * 40
    assert result.repositories[0].report_id == newest.id
    assert [e.classification for e in result.evidence_set.evidence] == [
        "background_workers"
    ]


# ------------------------------------------------------------- authorization


def test_other_users_repository_is_not_found(world, db):
    owner = world.user("owner@x.dev")
    attacker = world.user("attacker@x.dev")
    repo = world.repo(owner)
    world.report(repo, [API])

    with pytest.raises(RepositoryNotFoundError):
        provider(db, attacker).get([repo.id])


def test_nonexistent_repository_is_not_found(world, db):
    user = world.user("a@x.dev")
    with pytest.raises(RepositoryNotFoundError):
        provider(db, user).get([424242])


def test_private_repo_without_private_access_is_hidden_as_not_found(world, db):
    user = world.user("a@x.dev", private_enabled=False)
    repo = world.repo(user, private=True)
    world.report(repo, [API])

    with pytest.raises(RepositoryNotFoundError):
        provider(db, user).get([repo.id])


def test_private_repo_without_consent_is_denied(world, db):
    user = world.user("a@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.report(repo, [API])

    with pytest.raises(PrivateConsentRequiredError):
        provider(db, user).get([repo.id])


def test_private_repo_with_revoked_consent_is_denied(world, db):
    user = world.user("a@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.consent(user, repo, revoked=True)
    world.verification(user, repo)
    world.report(repo, [API])

    with pytest.raises(PrivateConsentRequiredError):
        provider(db, user).get([repo.id])


def test_private_repo_with_valid_consent_is_allowed_without_leaking_content(world, db):
    user = world.user("a@x.dev", private_enabled=True)
    repo = world.repo(user, private=True)
    world.consent(user, repo)
    world.verification(user, repo)
    world.report(repo, [API])

    result = provider(db, user).get([repo.id])

    assert result.status == ArchitectureStatus.AVAILABLE
    blob = repr(result)
    assert SECRET_CONTENT not in blob and SECRET_RATIONALE not in blob


def test_implicit_scope_skips_private_without_consent_but_keeps_public(world, db):
    user = world.user("a@x.dev", private_enabled=True)
    public = world.repo(user)
    private = world.repo(user, private=True)  # không consent
    world.verification(user, public)
    world.report(public, [API])
    world.report(private, [WORKERS])

    result = provider(db, user).get(None)

    assert result.status == ArchitectureStatus.AVAILABLE
    assert result.evidence_set.repository_ids == [str(public.id)]
    assert {e.repository_id for e in result.evidence_set.evidence} == {public.id}
    skipped = [r for r in result.repositories if r.repository_id == private.id]
    assert (
        skipped[0].status == RepositoryEvidenceStatus.SKIPPED_PRIVATE_CONSENT_REQUIRED
    )
    assert "PRIVATE_REPOSITORY_SKIPPED" in codes(result)
    assert private.id not in result.repository_ids


def test_implicit_scope_never_includes_other_users_repositories(world, db):
    mine = world.user("a@x.dev")
    other = world.user("b@x.dev")
    my_repo = world.repo(mine)
    other_repo = world.repo(other)
    world.verification(mine, my_repo)
    world.report(my_repo, [API])
    world.report(other_repo, [WORKERS])

    result = provider(db, mine).get(None)

    assert {e.repository_id for e in result.evidence_set.evidence} == {my_repo.id}


def test_no_repositories_gives_no_accessible_repository(world, db):
    user = world.user("a@x.dev")
    result = provider(db, user).get(None)
    assert result.status == ArchitectureStatus.NO_ACCESSIBLE_REPOSITORY
    assert result.evidence_set is None


def test_multi_repo_context_has_no_single_commit(world, db):
    user = world.user("a@x.dev")
    r1, r2 = world.repo(user), world.repo(user)
    for r in (r1, r2):
        world.verification(user, r)
    world.report(r1, [API], commit="1" * 40)
    world.report(r2, [WORKERS], commit="2" * 40)

    result = provider(db, user).get([r1.id, r2.id])

    assert result.evidence_set.commit_sha is None
    assert result.evidence_set.repository_ids == [str(r1.id), str(r2.id)]


def test_evidence_row_limit_is_enforced_and_reported(world, db):
    user = world.user("a@x.dev")
    repo = world.repo(user)
    world.verification(user, repo)
    world.report(repo, [API, WORKERS, API[:1] + ("other.py", "source_code")])
    policy = ArchitectureEvidencePolicy(max_evidence_rows_per_report=2)

    result = provider(db, user, policy).get([repo.id])

    assert len(result.evidence_set.evidence) == 2
    assert "ARCHITECTURE_EVIDENCE_TRUNCATED" in codes(result)
