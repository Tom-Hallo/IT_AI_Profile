"""Tests cho DatabaseSkillSnapshotSource với repo_id_filter (PBI-018)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.modules.role_scoring.skill_adapter import DatabaseSkillSnapshotSource


def _make_score(
    *,
    id: int,
    user_id: int = 1,
    repository_id: int = 10,
    technology: str = "python",
    status: str = "Scored",
    score: int = 80,
    commit_sha: str | None = "abc123",
    explanation: str | None = "ok",
) -> MagicMock:
    s = MagicMock()
    s.id = id
    s.user_id = user_id
    s.repository_id = repository_id
    s.technology = technology
    s.status = status
    s.score = score
    s.commit_sha = commit_sha
    s.explanation = explanation
    s.created_at = None
    return s


class TestDatabaseSkillSnapshotSourceScopeFilter:
    """DatabaseSkillSnapshotSource với repo_id_filter."""

    def _make_db(self, scores: list) -> MagicMock:
        db = MagicMock()
        db.scalars.return_value.all.return_value = scores
        db.execute.return_value.all.return_value = []  # no evidence links
        return db

    def test_no_filter_returns_all_scores(self) -> None:
        s1 = _make_score(id=1, repository_id=10)
        s2 = _make_score(id=2, repository_id=20)
        db = self._make_db([s1, s2])

        source = DatabaseSkillSnapshotSource(db)
        result = source.fetch(1)

        assert result is not None
        assert len(result.payload.items) == 2  # type: ignore[union-attr]

    def test_public_filter_excludes_private_repos(self) -> None:
        s_public = _make_score(id=1, repository_id=10)
        db = self._make_db([s_public])

        # filter chỉ cho phép repo 10 (public)
        source = DatabaseSkillSnapshotSource(db, repo_id_filter=frozenset({10}))
        result = source.fetch(1)

        assert result is not None
        items = result.payload.items  # type: ignore[union-attr]
        assert len(items) == 1
        assert items[0].skill_key == "python"

    def test_private_filter_excludes_public_repos(self) -> None:
        s_private = _make_score(id=2, repository_id=20, technology="typescript")
        db = self._make_db([s_private])

        source = DatabaseSkillSnapshotSource(db, repo_id_filter=frozenset({20}))
        result = source.fetch(1)

        assert result is not None
        items = result.payload.items  # type: ignore[union-attr]
        assert len(items) == 1
        assert items[0].skill_key == "typescript"

    def test_empty_filter_set_returns_none(self) -> None:
        """Filter rỗng → không lấy scores nào → None."""
        db = self._make_db([])

        source = DatabaseSkillSnapshotSource(db, repo_id_filter=frozenset())
        result = source.fetch(1)

        assert result is None

    def test_filter_with_no_matching_repos_returns_none(self) -> None:
        """Tất cả scores đều bị exclude bởi filter → DB scalars trả rỗng → None."""
        db = self._make_db([])

        source = DatabaseSkillSnapshotSource(db, repo_id_filter=frozenset({999}))
        result = source.fetch(1)

        assert result is None

    def test_snapshot_ref_set_from_param(self) -> None:
        s1 = _make_score(id=1)
        db = self._make_db([s1])

        source = DatabaseSkillSnapshotSource(db, repo_id_filter=frozenset({10}))
        result = source.fetch(1, snapshot_ref="my_ref")

        assert result is not None
        assert result.payload.snapshot_ref == "my_ref"  # type: ignore[union-attr]

    def test_snapshot_ref_default_includes_user_id(self) -> None:
        s1 = _make_score(id=1, user_id=42)
        db = self._make_db([s1])

        source = DatabaseSkillSnapshotSource(db)
        result = source.fetch(42)

        assert result is not None
        assert "42" in result.payload.snapshot_ref  # type: ignore[union-attr]
